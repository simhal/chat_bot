from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
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


class Settings(BaseSettings):
    linkedin_client_id: str = ""
    linkedin_client_secret: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"  # Can be: gpt-4o, gpt-4o-mini, gpt-4-turbo, gpt-3.5-turbo
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


settings = Settings()

app = FastAPI(title="Chatbot API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()


class ChatMessage(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str


class TokenExchangeRequest(BaseModel):
    code: str
    redirect_uri: str


class TokenExchangeResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 86400  # 24 hours


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = None


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """
    Verify custom JWT access token and return user payload.
    Uses Redis cache for fast validation.
    """
    token = credentials.credentials

    payload = verify_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """
    Dependency to require admin scope.
    """
    scopes = user.get("scopes", [])
    if "admin" not in scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return user


@app.get("/")
async def root():
    return {"message": "Chatbot API is running"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


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

            if user:
                # Update existing user
                user.linkedin_sub = linkedin_sub  # Update linkedin_sub in case it was a dummy value
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
    user: dict = Depends(get_current_user)
):
    """
    Chat endpoint with LangChain agent and Redis-backed conversation memory.
    Each user has isolated conversation context stored in Redis.
    """
    try:
        from chatbot_agent import ChatbotAgent

        # Get user ID from JWT token
        user_id = user.get("sub")

        # Create agent for this user (with Redis-backed memory)
        agent = ChatbotAgent(user_id)

        # Process message with conversation context
        response_text = agent.chat(chat_message.message)

        return ChatResponse(response=response_text)

    except Exception as e:
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
        from chatbot_agent import ChatbotAgent

        user_id = user.get("sub")
        agent = ChatbotAgent(user_id)
        history = agent.get_history()

        return {"history": history}

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
        from chatbot_agent import ChatbotAgent

        user_id = user.get("sub")
        agent = ChatbotAgent(user_id)
        agent.clear_history()

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
            "created_at": user.created_at.isoformat()
        }
        for user in users
    ]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
