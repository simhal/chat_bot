from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from jose import jwt, JWTError
import httpx
from typing import Optional, List
from sqlalchemy.orm import Session
from datetime import datetime
import os

from database import get_db
from models import User, Group
from auth import create_access_token, create_refresh_token, verify_access_token, verify_refresh_token, revoke_access_token, revoke_refresh_token

# Import shared state models for API
from agents import NavigationContextModel

# Import API routers (will be included after app initialization)
# from api.admin_prompts import router as admin_prompts_router
from api.user_profile import router as user_profile_router


class Settings(BaseSettings):
    linkedin_client_id: str = ""
    linkedin_client_secret: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"  # Can be: gpt-4o, gpt-4o-mini, gpt-4-turbo, gpt-3.5-turbo
    google_api_key: str = ""  # For Google Custom Search API
    google_search_engine_id: str = ""  # Custom Search Engine ID
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


settings = Settings()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add security headers to all responses.

    Implements OWASP recommended security headers:
    - X-Frame-Options: Prevents clickjacking attacks
    - X-Content-Type-Options: Prevents MIME type sniffing
    - X-XSS-Protection: Legacy XSS filter (still useful for older browsers)
    - Strict-Transport-Security: Enforces HTTPS connections
    - Content-Security-Policy: Restricts resource loading (API-appropriate policy)
    - Referrer-Policy: Controls referrer information leakage
    - Permissions-Policy: Restricts browser feature access

    Note: Public resource endpoints (/api/r/) are allowed to be embedded in iframes
    from the same origin to support article HTML rendering in the frontend.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Check if this is a public resource endpoint that needs to be embeddable
        is_embeddable_resource = request.url.path.startswith("/api/r/")

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Enable browser XSS filter (legacy but still useful)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Enforce HTTPS (1 year, include subdomains)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # Control referrer information
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Restrict browser features
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), camera=(), geolocation=(), "
            "gyroscope=(), magnetometer=(), microphone=(), "
            "payment=(), usb=()"
        )

        if is_embeddable_resource:
            # For public resource endpoints, allow embedding from frontend origins
            # This is needed for article HTML to be shown in iframe on the frontend
            # Get allowed origins from CORS settings
            allowed_origins = settings.cors_origins.split(",")
            frame_ancestors = " ".join(allowed_origins) + " 'self'"

            # Allow framing from frontend origins (not DENY or SAMEORIGIN)
            # X-Frame-Options doesn't support multiple origins, so we rely on CSP frame-ancestors
            # Remove X-Frame-Options to avoid conflicts with CSP
            if "X-Frame-Options" in response.headers:
                del response.headers["X-Frame-Options"]

            # CSP for embeddable HTML content - allow styles, scripts, images, and framing from frontend
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "style-src 'self' 'unsafe-inline'; "
                "script-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https:; "
                f"frame-ancestors {frame_ancestors}"
            )
        else:
            # For all other endpoints, deny framing (prevent clickjacking)
            response.headers["X-Frame-Options"] = "DENY"
            # Restrictive CSP for API endpoints
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"

        return response


app = FastAPI(title="Chatbot API")

# Log configuration on startup
import logging
logger = logging.getLogger("uvicorn")

@app.on_event("startup")
async def startup_event():
    """Log important configuration on startup."""
    from observability import configure_langsmith, log_langsmith_status

    logger.info("=" * 60)
    logger.info("Chatbot API Starting Up")
    logger.info("=" * 60)
    logger.info(f"OpenAI Model: {settings.openai_model}")
    logger.info("Multi-Agent System: ENABLED")
    logger.info(f"Google Search Available: {bool(settings.google_api_key and settings.google_search_engine_id)}")

    # Configure LangSmith observability
    configure_langsmith()
    log_langsmith_status()

    logger.info("=" * 60)

# Security headers middleware (must be added before CORS to wrap responses)
app.add_middleware(SecurityHeadersMiddleware)

# CORS middleware with tightened configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
)

security = HTTPBearer()


class ChatMessage(BaseModel):
    message: str
    navigation_context: Optional[NavigationContextModel] = None


class ArticleReference(BaseModel):
    id: int
    topic: str
    headline: str


class NavigationCommand(BaseModel):
    """Navigation command that the chat can issue to control the UI."""
    action: str  # navigate, logout, create_article
    target: Optional[str] = None  # URL path or section name
    params: Optional[dict] = None  # Additional parameters (topic, article_id, etc.)


class LinkedResource(BaseModel):
    """Resource linked to an article."""
    resource_id: int
    name: str
    type: str
    hash_id: Optional[str] = None
    already_linked: Optional[bool] = False


class EditorContent(BaseModel):
    """Content to fill into the article editor UI (not displayed in chat)."""
    headline: Optional[str] = None
    content: Optional[str] = None
    keywords: Optional[str] = None
    action: str = "fill"  # fill, append, replace
    linked_resources: Optional[List[LinkedResource]] = None
    article_id: Optional[int] = None


class UIAction(BaseModel):
    """UI action command that the chat can trigger (button clicks, tab switches, etc.)."""
    type: str  # Action type: submit_for_review, save_draft, switch_view_*, etc.
    params: Optional[dict] = None  # Action parameters (article_id, topic, etc.)


class ConfirmationPrompt(BaseModel):
    """HITL confirmation prompt - displays confirm/cancel buttons in chat."""
    id: str  # Unique ID for this confirmation
    type: str  # Confirmation type (e.g., 'publish_approval', 'delete_article')
    title: str  # Short title (e.g., "Confirm Publication")
    message: str  # Explanation of what will happen
    article_id: Optional[int] = None  # Related article ID
    confirm_label: str  # Button label (e.g., "Publish Now")
    cancel_label: str  # Button label (e.g., "Cancel")
    confirm_endpoint: str  # API endpoint to call on confirm
    confirm_method: Optional[str] = "POST"  # HTTP method
    confirm_body: Optional[dict] = None  # Request body for confirm


class ChatResponse(BaseModel):
    response: str
    agent_type: Optional[str] = None  # Which specialist handled the query
    routing_reason: Optional[str] = None  # Why this specialist was selected
    articles: Optional[List[ArticleReference]] = None  # Referenced articles
    navigation: Optional[NavigationCommand] = None  # Navigation command for the UI
    editor_content: Optional[EditorContent] = None  # Content to fill into editor (not chat)
    ui_action: Optional[UIAction] = None  # UI action to trigger (button clicks, etc.)
    confirmation: Optional[ConfirmationPrompt] = None  # HITL confirmation prompt with buttons


class TokenExchangeRequest(BaseModel):
    code: str
    redirect_uri: str


class TokenExchangeResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 86400  # 24 hours
    user: Optional[dict] = None  # User info for client


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = None


# Import shared dependencies from dependencies module
from dependencies import get_current_user, require_admin


# Include API routers for multi-agent system
# All routers now use shared dependencies from dependencies.py - no monkey-patching needed!
try:
    from api.admin_prompts import router as admin_prompts_router
    from api.user import router as user_router
    from api.content import router as content_router
    from api.prompts import router as prompts_router
    from api.resources import router as resources_router, public_router as public_resources_router
    from api.topics import router as topics_router
    from api.reader import router as reader_router
    from api.analyst import router as analyst_router
    from api.editor import router as editor_router
    from api.admin import topic_router as admin_topic_router, global_router as admin_global_router

    # Core routers
    app.include_router(admin_prompts_router)
    app.include_router(user_router)
    app.include_router(user_profile_router)  # /api/profile/...
    app.include_router(prompts_router)
    app.include_router(topics_router)

    # Role-based content routers
    app.include_router(reader_router)      # /api/reader/{topic}/...
    app.include_router(analyst_router)     # /api/analyst/{topic}/...
    app.include_router(editor_router)      # /api/editor/{topic}/...
    app.include_router(admin_topic_router)   # /api/admin/{topic}/...
    app.include_router(admin_global_router)  # /api/admin/global/...

    # Resource routers (authenticated + public)
    app.include_router(resources_router)
    app.include_router(public_resources_router)

    # Legacy content router (to be removed after migration)
    app.include_router(content_router)

    logger.info("API routers loaded: admin_prompts, user, prompts, topics, reader, analyst, editor, admin (topic+global), resources")
except ImportError as e:
    print(f"Warning: Multi-agent API routers not available: {e}")

# Include new multi-agent workflow routers
try:
    from api.approvals import router as approvals_router
    from api.websocket import router as websocket_router

    app.include_router(approvals_router)
    app.include_router(websocket_router)
    logger.info("Multi-agent workflow routers loaded: approvals, websocket")
except ImportError as e:
    print(f"Warning: Multi-agent workflow routers not available: {e}")


@app.get("/")
async def root():
    return {"message": "Chatbot API is running"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/api/health/vectordb")
async def vectordb_health():
    """Check ChromaDB health and statistics."""
    from services.vector_service import VectorService

    stats = VectorService.get_collection_stats()
    return stats


@app.get("/debug/settings")
async def debug_settings():
    """Debug endpoint to check if settings are loaded (without exposing secrets)"""
    return {
        "linkedin_client_id": settings.linkedin_client_id[:5] + "..." if settings.linkedin_client_id else "NOT SET",
        "linkedin_client_secret_present": bool(settings.linkedin_client_secret),
        "openai_api_key_present": bool(settings.openai_api_key),
        "openai_model": settings.openai_model,
        "cors_origins": settings.cors_origins,
        "working_directory": os.getcwd(),
        "env_file_exists": os.path.exists(".env")
    }


# =============================================================================
# Dev/Test Login Endpoint (only available when TESTING=true)
# =============================================================================

class DevLoginRequest(BaseModel):
    """Request body for dev login."""
    email: str


@app.post("/api/auth/dev-login", response_model=TokenExchangeResponse)
async def dev_login(request: DevLoginRequest, db: Session = Depends(get_db)):
    """
    Development/test login endpoint - bypasses LinkedIn OAuth.
    ONLY available when TESTING environment variable is set to 'true'.

    This endpoint allows E2E tests to authenticate as test users without
    going through the full OAuth flow.
    """
    # Security: Only allow in test environment
    if os.environ.get("TESTING", "").lower() != "true":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found"
        )

    # Find user by email
    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Test user not found: {request.email}"
        )

    # Get user's groups (User.groups is the relationship)
    groups = [g.name for g in user.groups]

    # Create tokens
    access_token, _ = create_access_token(user, groups)
    refresh_token = create_refresh_token(user.id)

    return TokenExchangeResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="Bearer",
        user={
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "surname": user.surname,
            "picture": user.picture,
            "scopes": groups
        }
    )


@app.post("/api/auth/token", response_model=TokenExchangeResponse)
async def exchange_token(request: TokenExchangeRequest, db: Session = Depends(get_db)):
    """
    Exchange LinkedIn authorization code for custom JWT tokens.
    Creates or updates user in database and assigns default 'user' group.
    Returns custom access and refresh tokens with user's groups/scopes.
    """
    try:
        # Prepare form data
        form_data = {
            "grant_type": "authorization_code",
            "code": request.code,
            "client_id": settings.linkedin_client_id,
            "client_secret": settings.linkedin_client_secret,
            "redirect_uri": request.redirect_uri
        }

        # Debug: log values
        import logging
        logger = logging.getLogger("uvicorn")
        logger.info(f"Exchanging token with client_id: {settings.linkedin_client_id}")
        logger.info(f"Client secret present: {bool(settings.linkedin_client_secret)}")
        logger.info(f"Redirect URI: {request.redirect_uri}")

        # Exchange code for LinkedIn tokens
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://www.linkedin.com/oauth/v2/accessToken",
                data=form_data
            )

            if not response.is_success:
                error_data = response.json()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"LinkedIn token exchange failed: {error_data.get('error_description', 'Unknown error')}"
                )

            linkedin_tokens = response.json()

            if "id_token" not in linkedin_tokens:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No ID token received from LinkedIn"
                )

            # Verify and decode LinkedIn ID token
            id_token = linkedin_tokens["id_token"]
            async with httpx.AsyncClient() as client:
                jwks_response = await client.get("https://www.linkedin.com/oauth/openid/jwks")
                jwks = jwks_response.json()

            unverified_header = jwt.get_unverified_header(id_token)

            # Find the correct key
            rsa_key = {}
            for key in jwks["keys"]:
                if key["kid"] == unverified_header["kid"]:
                    rsa_key = {
                        "kty": key["kty"],
                        "kid": key["kid"],
                        "n": key["n"],
                        "e": key["e"]
                    }
                    if "use" in key:
                        rsa_key["use"] = key["use"]
                    break

            if not rsa_key:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Unable to find appropriate key"
                )

            # Verify and decode the token
            linkedin_payload = jwt.decode(
                id_token,
                rsa_key,
                algorithms=["RS256"],
                audience=settings.linkedin_client_id,
                options={"verify_aud": True}
            )

            # Extract user information from LinkedIn token
            linkedin_sub = linkedin_payload.get("sub")
            email = linkedin_payload.get("email")
            name = linkedin_payload.get("given_name", linkedin_payload.get("name", ""))
            surname = linkedin_payload.get("family_name", "")
            picture = linkedin_payload.get("picture")

            if not linkedin_sub or not email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="LinkedIn token missing required user information"
                )

            # Create or update user in database
            # First check by LinkedIn sub
            user = db.query(User).filter(User.linkedin_sub == linkedin_sub).first()

            if not user:
                # If not found by linkedin_sub, check by email (for existing users from seed or other sources)
                user = db.query(User).filter(User.email == email).first()

                if user and user.linkedin_sub and user.linkedin_sub != linkedin_sub:
                    # Check if this is a placeholder linkedin_sub that can be claimed
                    is_claimable = (
                        user.linkedin_sub.startswith("admin_") or
                        user.linkedin_sub.startswith("seed_") or
                        user.linkedin_sub.startswith("pending_")
                    )
                    if not is_claimable:
                        # User exists with same email but different linkedin_sub
                        # This is a conflict - email must be unique
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail=f"Email {email} is already registered with a different LinkedIn account"
                        )

            if user:
                # Update existing user
                # Only update linkedin_sub if it's empty or a placeholder (allows pre-created users to be claimed)
                if not user.linkedin_sub or user.linkedin_sub.startswith("admin_") or user.linkedin_sub.startswith("seed_") or user.linkedin_sub.startswith("pending_"):
                    user.linkedin_sub = linkedin_sub
                    logger.info(f"Updated linkedin_sub for user: {email}")

                user.email = email
                user.name = name
                user.surname = surname
                user.picture = picture
                logger.info(f"Updated existing user: {email}")
            else:
                # Create new user
                user = User(
                    linkedin_sub=linkedin_sub,
                    email=email,
                    name=name,
                    surname=surname,
                    picture=picture
                )
                db.add(user)
                db.flush()  # Get the user ID

                # Assign default 'user' group
                default_group = db.query(Group).filter(Group.name == "user").first()
                if default_group:
                    user.groups.append(default_group)

                logger.info(f"Created new user: {email}")

            # Update access tracking
            user.access_count = (user.access_count or 0) + 1
            user.last_access_at = datetime.utcnow()

            db.commit()
            db.refresh(user)

            # Check if user account is active
            if not user.active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account is inactive. Please contact an administrator."
                )

            # Get user's groups/scopes
            user_groups = [group.name for group in user.groups]

            # Create custom JWT tokens
            access_token, _ = create_access_token(user, user_groups)
            refresh_token = create_refresh_token(user.id)

            return TokenExchangeResponse(
                access_token=access_token,
                refresh_token=refresh_token
            )

    except HTTPException:
        raise
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate LinkedIn credentials: {str(e)}"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Token exchange error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Token exchange error: {str(e)}"
        )


@app.post("/api/auth/refresh", response_model=TokenExchangeResponse)
async def refresh_access_token(request: RefreshTokenRequest, db: Session = Depends(get_db)):
    """
    Refresh access token using a valid refresh token.
    Returns new access and refresh tokens.
    """
    user_id = verify_refresh_token(request.refresh_token)

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )

    # Get user from database
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    # Check if user account is active
    if not user.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive. Please contact an administrator."
        )

    # Update access tracking (token refresh counts as an access)
    user.access_count = (user.access_count or 0) + 1
    user.last_access_at = datetime.utcnow()
    db.commit()
    db.refresh(user)

    # Get user's groups/scopes
    user_groups = [group.name for group in user.groups]

    # Create new tokens
    access_token, _ = create_access_token(user, user_groups)
    new_refresh_token = create_refresh_token(user.id)

    return TokenExchangeResponse(
        access_token=access_token,
        refresh_token=new_refresh_token
    )


@app.post("/api/auth/logout")
async def logout(
    request: LogoutRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Logout user by revoking access and refresh tokens.
    Removes tokens from Redis cache, making them immediately invalid.
    """
    # Get access token from Authorization header
    access_token = credentials.credentials

    # Revoke access token
    revoke_access_token(access_token)

    # Revoke refresh token if provided
    if request.refresh_token:
        revoke_refresh_token(request.refresh_token)

    return {"message": "Successfully logged out"}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(
    chat_message: ChatMessage,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Chat endpoint with multi-agent financial analyst system.
    Routes to specialized agents based on query content.
    """
    try:
        # Get user ID from JWT token
        user_id = int(user.get("sub"))

        # Multi-agent content system
        from services.agent_service import AgentService
        from services.user_context_service import UserContextService

        # Build user context from JWT payload and database
        user_context = UserContextService.build(user, db)

        # Use Pydantic model's to_dict() for clean conversion
        nav_context = None
        if chat_message.navigation_context:
            nav_context = chat_message.navigation_context.to_dict()
            logger.info(f"📍 Chat API - Navigation context received: section={nav_context.get('section')}, role={nav_context.get('role')}, article_id={nav_context.get('article_id')}")

        agent_service = AgentService(user_id, db, user_context=user_context)

        # Process message with routing to content agents
        result = agent_service.chat(chat_message.message, navigation_context=nav_context)

        # Format response with article references
        response_text = result["response"]
        articles = result.get("articles", [])
        article_references = []

        # Add article references at the end if available
        if articles:
            response_text += "\n\n---\n**References:**\n"
            for article in articles:
                topic = article['topic']
                article_id = article['id']
                headline = article['headline']
                response_text += f"\n- [{headline}](/?tab={topic}#article-{article_id})"

                # Build article reference list
                article_references.append(ArticleReference(
                    id=article_id,
                    topic=topic,
                    headline=headline
                ))

        # Build navigation command if present
        nav_command = None
        if result.get("navigation"):
            nav = result["navigation"]
            nav_command = NavigationCommand(
                action=nav.get("action", "navigate"),
                target=nav.get("target"),
                params=nav.get("params")
            )

        # Build editor content if present (content to fill into editor UI, not chat)
        editor_content = None
        if result.get("editor_content"):
            ec = result["editor_content"]
            # Convert linked resources to LinkedResource objects
            linked_resources = None
            if ec.get("linked_resources"):
                linked_resources = [
                    LinkedResource(
                        resource_id=r.get("resource_id"),
                        name=r.get("name", ""),
                        type=r.get("type", ""),
                        hash_id=r.get("hash_id"),
                        already_linked=r.get("already_linked", False)
                    )
                    for r in ec["linked_resources"]
                ]
            editor_content = EditorContent(
                headline=ec.get("headline"),
                content=ec.get("content"),
                keywords=ec.get("keywords"),
                action=ec.get("action", "fill"),
                linked_resources=linked_resources,
                article_id=ec.get("article_id")
            )

        # Build UI action if present
        ui_action = None
        if result.get("ui_action"):
            ua = result["ui_action"]
            ui_action = UIAction(
                type=ua.get("type"),
                params=ua.get("params")
            )
            logger.info(f"🎯 Chat API - Returning ui_action: type={ui_action.type}, params={ui_action.params}")

        # Build HITL confirmation if present
        confirmation = None
        if result.get("confirmation"):
            conf = result["confirmation"]
            confirmation = ConfirmationPrompt(
                id=conf.get("id", ""),
                type=conf.get("type", ""),
                title=conf.get("title", "Confirm"),
                message=conf.get("message", ""),
                article_id=conf.get("article_id"),
                confirm_label=conf.get("confirm_label", "Confirm"),
                cancel_label=conf.get("cancel_label", "Cancel"),
                confirm_endpoint=conf.get("confirm_endpoint", ""),
                confirm_method=conf.get("confirm_method", "POST"),
                confirm_body=conf.get("confirm_body", {})
            )
            logger.info(f"🔔 Chat API - Returning confirmation: type={confirmation.type}, endpoint={confirmation.confirm_endpoint}")

        # Log the final response structure
        if editor_content:
            logger.info(f"📤 Chat API - Returning editor_content: headline={editor_content.headline[:50] if editor_content.headline else 'None'}, content_len={len(editor_content.content or '')}, action={editor_content.action}")

        return ChatResponse(
            response=response_text,
            agent_type=result.get("agent_type"),
            routing_reason=result.get("routing_reason"),
            articles=article_references if article_references else None,
            navigation=nav_command,
            editor_content=editor_content,
            ui_action=ui_action,
            confirmation=confirmation
        )

    except Exception as e:
        import traceback
        logger.error(f"[CHAT ERROR] User: {user.get('sub')}, Message: {chat_message.message[:50]}...")
        logger.error(f"[CHAT ERROR] Exception: {str(e)}")
        logger.error(f"[CHAT ERROR] Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error in chatbot: {str(e)}"
        )


@app.get("/api/chat/history")
async def get_chat_history(user: dict = Depends(get_current_user)):
    """
    Get conversation history for the current user.
    """
    try:
        from conversation_memory import create_conversation_memory

        user_id = user.get("sub")
        message_history = create_conversation_memory(int(user_id))
        chat_history = message_history.messages

        # Format messages for response
        messages = []
        for msg in chat_history:
            if hasattr(msg, 'content'):
                role = "user" if msg.__class__.__name__ == "HumanMessage" else "assistant"
                messages.append({"role": role, "content": msg.content})

        return {"history": messages}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving chat history: {str(e)}"
        )


@app.delete("/api/chat/history")
async def clear_chat_history(user: dict = Depends(get_current_user)):
    """
    Clear conversation history for the current user.
    """
    try:
        from conversation_memory import clear_conversation_history

        user_id = user.get("sub")
        clear_conversation_history(int(user_id))

        return {"message": "Chat history cleared successfully"}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error clearing chat history: {str(e)}"
        )


@app.get("/api/me")
async def get_user_info(user: dict = Depends(get_current_user)):
    """
    Returns the authenticated user's information from the custom JWT token.
    """
    return {
        "id": user.get("sub"),
        "name": user.get("name"),
        "surname": user.get("surname"),
        "email": user.get("email"),
        "picture": user.get("picture"),
        "scopes": user.get("scopes", [])
    }


# Admin endpoints for group management


class CreateGroupRequest(BaseModel):
    name: str
    description: Optional[str] = None


class AssignGroupRequest(BaseModel):
    user_id: int
    group_name: str


@app.post("/api/admin/groups")
async def create_group(
    request: CreateGroupRequest,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    Create a new group. Requires admin scope.
    """
    # Check if group already exists
    existing_group = db.query(Group).filter(Group.name == request.name).first()
    if existing_group:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Group '{request.name}' already exists"
        )

    group = Group(name=request.name, description=request.description)
    db.add(group)
    db.commit()
    db.refresh(group)

    return {
        "id": group.id,
        "name": group.name,
        "description": group.description
    }


@app.get("/api/admin/groups")
async def list_groups(
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    List all groups. Requires admin scope.
    """
    groups = db.query(Group).all()
    return [
        {
            "id": group.id,
            "name": group.name,
            "description": group.description,
            "user_count": len(group.users)
        }
        for group in groups
    ]


@app.post("/api/admin/users/{user_id}/groups")
async def assign_group_to_user(
    user_id: int,
    request: AssignGroupRequest,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    Assign a group to a user. Requires admin scope.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    group = db.query(Group).filter(Group.name == request.group_name).first()
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group '{request.group_name}' not found"
        )

    # Check if user already has this group
    if group in user.groups:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User already has group '{request.group_name}'"
        )

    user.groups.append(group)
    db.commit()

    return {
        "message": f"Group '{request.group_name}' assigned to user {user.email}",
        "user_groups": [g.name for g in user.groups]
    }


@app.delete("/api/admin/users/{user_id}/groups/{group_name}")
async def remove_group_from_user(
    user_id: int,
    group_name: str,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    Remove a group from a user. Requires admin scope.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    group = db.query(Group).filter(Group.name == group_name).first()
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group '{group_name}' not found"
        )

    # Check if user has this group
    if group not in user.groups:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User does not have group '{group_name}'"
        )

    user.groups.remove(group)
    db.commit()

    return {
        "message": f"Group '{group_name}' removed from user {user.email}",
        "user_groups": [g.name for g in user.groups]
    }


@app.get("/api/admin/users")
async def list_users(
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    List all users with their groups. Requires admin scope.
    """
    users = db.query(User).all()
    return [
        {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "surname": user.surname,
            "groups": [g.name for g in user.groups],
            "created_at": user.created_at.isoformat(),
            "active": user.active,
            "last_access_at": user.last_access_at.isoformat() if user.last_access_at else None,
            "is_pending": user.linkedin_sub.startswith("pending_") if user.linkedin_sub else True
        }
        for user in users
    ]


class CreateUserRequest(BaseModel):
    email: str
    name: Optional[str] = None
    surname: Optional[str] = None


@app.post("/api/admin/users")
async def create_user(
    request: CreateUserRequest,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    Create a new user manually (before OAuth login).
    The user will have a placeholder linkedin_sub until they log in via OAuth.
    Requires admin scope.
    """
    # Check if email already exists
    existing_user = db.query(User).filter(User.email == request.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User with email {request.email} already exists"
        )

    # Create user with placeholder linkedin_sub
    import uuid
    placeholder_sub = f"pending_{uuid.uuid4().hex[:16]}"

    user = User(
        email=request.email,
        name=request.name,
        surname=request.surname,
        linkedin_sub=placeholder_sub,
        active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info(f"Admin created user: {request.email}")

    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "surname": user.surname,
        "groups": [],
        "created_at": user.created_at.isoformat(),
        "active": user.active,
        "is_pending": True
    }


@app.put("/api/admin/users/{user_id}/ban")
async def ban_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    Ban a user (set active=False). Requires admin scope.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Don't allow banning yourself
    admin_user_id = int(admin.get("sub", 0))
    if user.id == admin_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot ban yourself"
        )

    user.active = False
    db.commit()

    logger.info(f"Admin banned user: {user.email}")

    return {"message": f"User {user.email} has been banned", "active": False}


@app.put("/api/admin/users/{user_id}/unban")
async def unban_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    Unban a user (set active=True). Requires admin scope.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    user.active = True
    db.commit()

    logger.info(f"Admin unbanned user: {user.email}")

    return {"message": f"User {user.email} has been unbanned", "active": True}


@app.delete("/api/admin/users/{user_id}")
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    Delete a user. Requires admin scope.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Don't allow deleting yourself
    admin_user_id = int(admin.get("sub", 0))
    if user.id == admin_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete yourself"
        )

    email = user.email
    db.delete(user)
    db.commit()

    logger.info(f"Admin deleted user: {email}")

    return {"message": f"User {email} has been deleted"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
