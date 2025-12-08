# AI Chatbot with LinkedIn OAuth

A full-stack chatbot application featuring FastAPI backend, SvelteKit frontend, LinkedIn OAuth authentication, and OpenAI ChatGPT integration.

## Features

- **LinkedIn OAuth Authentication**: Secure authentication using LinkedIn's OpenID Connect with ID token validation
- **ChatGPT Integration**: Powered by OpenAI's ChatGPT models (GPT-4o, GPT-4o-mini, GPT-4-turbo, GPT-3.5-turbo)
- **Modern Stack**: FastAPI backend with SvelteKit frontend
- **Docker Support**: Complete Docker Compose setup for easy deployment
- **Security Best Practices**: Token-based authentication with JWT validation
- **Configurable Models**: Choose between different OpenAI models based on your needs

## Architecture

### Backend (FastAPI)
- FastAPI REST API
- LinkedIn OAuth ID token validation using JWKS
- OpenAI ChatGPT API integration
- Configurable model selection
- CORS support for frontend communication

### Frontend (SvelteKit)
- Modern SvelteKit application with TypeScript
- LinkedIn OAuth flow implementation
- Real-time chat interface
- Responsive design

## Prerequisites

- Docker and Docker Compose
- LinkedIn Developer Account (for OAuth credentials)
- OpenAI API Key

## Setup Instructions

### 1. LinkedIn OAuth App Setup

1. Go to [LinkedIn Developers](https://www.linkedin.com/developers/apps)
2. Create a new app
3. Under "Auth" tab, add redirect URL: `http://localhost:3000/auth/callback`
4. Note your Client ID and Client Secret
5. Enable OpenID Connect scopes: `openid`, `profile`, `email`

### 2. OpenAI ChatGPT API Key

1. Go to [OpenAI Platform](https://platform.openai.com/api-keys)
2. Create an API key from your account settings
3. Choose which model to use:
   - **gpt-4o-mini**: Recommended - Fast and cost-effective
   - **gpt-4o**: Most capable, higher cost
   - **gpt-4-turbo**: Balance of capability and speed
   - **gpt-3.5-turbo**: Fastest, lowest cost

### 3. Environment Configuration

#### Backend Environment Variables

Create `backend/.env` file:

```env
LINKEDIN_CLIENT_ID=your_linkedin_client_id
OPENAI_API_KEY=your_openai_chatgpt_api_key
OPENAI_MODEL=gpt-4o-mini
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

**Model Options:**
- `gpt-4o-mini` (recommended) - Fast, cost-effective
- `gpt-4o` - Most capable
- `gpt-4-turbo` - Balanced
- `gpt-3.5-turbo` - Fastest, cheapest

#### Frontend Environment Variables

Create `frontend/.env` file:

```env
PUBLIC_LINKEDIN_CLIENT_ID=your_linkedin_client_id
PUBLIC_LINKEDIN_REDIRECT_URI=http://localhost:3000/auth/callback
PUBLIC_API_URL=http://localhost:8000
```

## Running the Application

### Option 1: Docker Compose (Recommended)

```bash
# Build and start all services
docker-compose up --build

# Or run in detached mode
docker-compose up -d --build
```

The application will be available at:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Documentation: http://localhost:8000/docs

### Option 2: Local Development

#### Backend

```bash
cd backend

# Create .env file with your credentials
cp .env.example .env

# Install dependencies with uv
uv sync

# Run the server
uv run uvicorn main:app --reload --port 8000
```

#### Frontend

```bash
cd frontend

# Create .env file with your credentials
cp .env.example .env

# Install dependencies
npm install

# Run development server
npm run dev
```

## Usage

1. Open http://localhost:3000 (or http://localhost:5173 for local dev)
2. Click "Sign in with LinkedIn"
3. Authorize the application
4. Start chatting with the AI assistant

## API Endpoints

### Backend API

- `GET /` - Health check
- `GET /health` - Service health status
- `POST /api/chat` - Send message to chatbot (requires authentication)
- `GET /api/me` - Get authenticated user info (requires authentication)

## Security Features

- **ID Token Validation**: Backend validates LinkedIn ID tokens using JWKS
- **JWT Verification**: Proper signature and audience verification
- **Secure Token Storage**: Frontend stores tokens in localStorage with proper state management
- **CORS Protection**: Configured CORS policies for frontend-backend communication

## Technology Stack

### Backend
- **FastAPI**: Modern Python web framework
- **python-jose**: JWT token handling
- **httpx**: Async HTTP client
- **OpenAI**: AI model integration
- **uvicorn**: ASGI server
- **uv**: Fast Python package manager

### Frontend
- **SvelteKit**: Full-stack web framework
- **TypeScript**: Type-safe development
- **Svelte Stores**: State management
- **Vite**: Build tool

### DevOps
- **Docker**: Containerization
- **Docker Compose**: Multi-container orchestration

## Project Structure

```
chatbot-app/
├── backend/
│   ├── main.py              # FastAPI application
│   ├── pyproject.toml       # Python dependencies
│   ├── Dockerfile           # Backend container
│   └── .env.example         # Environment template
├── frontend/
│   ├── src/
│   │   ├── lib/
│   │   │   ├── stores/
│   │   │   │   └── auth.ts  # Authentication state
│   │   │   └── api.ts       # API client
│   │   └── routes/
│   │       ├── +page.svelte           # Main chat page
│   │       └── auth/callback/         # OAuth callback
│   ├── Dockerfile           # Frontend container
│   └── .env.example         # Environment template
├── docker-compose.yml       # Docker orchestration
└── README.md               # This file
```

## Troubleshooting

### OAuth Issues
- Ensure redirect URI matches exactly in LinkedIn app settings
- Check that Client ID is correct in both backend and frontend .env files

### API Connection Issues
- Verify CORS_ORIGINS includes your frontend URL
- Check that backend is running and accessible
- Review browser console for CORS errors

### Docker Issues
- Ensure ports 3000 and 8000 are not in use
- Run `docker-compose down -v` to clean up volumes
- Check logs: `docker-compose logs backend` or `docker-compose logs frontend`

## License

MIT

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.
