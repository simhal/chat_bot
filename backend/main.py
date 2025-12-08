from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from jose import jwt, JWTError
import httpx
from typing import Optional
import os


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
    id_token: str
    access_token: str
    expires_in: int


async def verify_linkedin_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """
    Verify LinkedIn ID token using LinkedIn's JWKS endpoint.
    In production, you should cache the JWKS keys.
    """
    token = credentials.credentials

    try:
        # Get LinkedIn's public keys
        async with httpx.AsyncClient() as client:
            response = await client.get("https://www.linkedin.com/oauth/openid/jwks")
            jwks = response.json()

        # Decode and verify the token
        # Note: python-jose will automatically verify signature using JWKS
        unverified_header = jwt.get_unverified_header(token)

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
                # "use" field is optional in JWKS
                if "use" in key:
                    rsa_key["use"] = key["use"]
                break

        if not rsa_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unable to find appropriate key"
            )

        # Verify and decode the token
        payload = jwt.decode(
            token,
            rsa_key,
            algorithms=["RS256"],
            audience=settings.linkedin_client_id,
            options={"verify_aud": True}
        )

        return payload

    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication error: {str(e)}"
        )


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
async def exchange_token(request: TokenExchangeRequest):
    """
    Exchange LinkedIn authorization code for tokens.
    This endpoint keeps the client_secret secure on the server.
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

            tokens = response.json()

            if "id_token" not in tokens:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No ID token received from LinkedIn"
                )

            return TokenExchangeResponse(
                id_token=tokens["id_token"],
                access_token=tokens["access_token"],
                expires_in=tokens["expires_in"]
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Token exchange error: {str(e)}"
        )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(
    chat_message: ChatMessage,
    user: dict = Depends(verify_linkedin_token)
):
    """
    Chat endpoint that requires LinkedIn OAuth authentication.
    Sends the message to OpenAI ChatGPT and returns the response.
    """
    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)

        # Call OpenAI ChatGPT API
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": chat_message.message}
            ],
            max_tokens=1000
        )

        assistant_message = response.choices[0].message.content

        return ChatResponse(response=assistant_message)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error calling OpenAI ChatGPT: {str(e)}"
        )


@app.get("/api/me")
async def get_user_info(user: dict = Depends(verify_linkedin_token)):
    """
    Returns the authenticated user's information from the token.
    """
    return {
        "sub": user.get("sub"),
        "name": user.get("name"),
        "email": user.get("email"),
        "picture": user.get("picture")
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
