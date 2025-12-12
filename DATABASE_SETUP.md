# Database and Authentication Setup

This document explains the PostgreSQL database, Redis cache, and OAuth2 authentication system implemented in this application.

## Overview

The application uses:
- **PostgreSQL** for persistent data storage (users, groups, relationships)
- **Redis** for token caching (fast authentication validation)
- **Custom JWT tokens** with OAuth2 scopes for authorization
- **LinkedIn OAuth** for initial user authentication

## Architecture

### Authentication Flow

1. User logs in via LinkedIn OAuth
2. Backend verifies LinkedIn ID token
3. Backend creates or updates user in PostgreSQL database
4. Backend assigns default 'user' group to new users
5. Backend generates custom JWT access token with user's groups/scopes
6. Backend generates refresh token for token renewal
7. Tokens are cached in Redis for fast validation
8. Frontend stores tokens and uses them for API requests
9. Frontend automatically refreshes expired tokens

### Database Schema

#### Users Table
- `id`: Primary key
- `email`: User's email (unique)
- `name`: User's first name
- `surname`: User's last name
- `linkedin_sub`: LinkedIn user ID (unique)
- `picture`: Profile picture URL
- `created_at`: Timestamp
- `updated_at`: Timestamp

#### Groups Table
- `id`: Primary key
- `name`: Group name (unique)
- `description`: Group description
- `created_at`: Timestamp

#### UserGroups Table (Many-to-Many)
- `user_id`: Foreign key to Users
- `group_id`: Foreign key to Groups
- `assigned_at`: Timestamp

### Token System

#### Access Token
- **Lifetime**: 24 hours
- **Contains**: User ID, email, name, surname, picture, scopes (groups)
- **Storage**: Redis cache
- **Usage**: All API requests

#### Refresh Token
- **Lifetime**: 7 days
- **Contains**: User ID only
- **Storage**: Redis cache
- **Usage**: Renewing access tokens

## Setup Instructions

### 1. Start PostgreSQL and Redis

Start the database and cache services separately:

```bash
# Start PostgreSQL
docker-compose up -d postgres

# Start Redis
docker-compose up -d redis

# Verify they're running
docker-compose ps
```

### 2. Configure Environment Variables

Copy the example environment file and fill in the required values:

```bash
cd backend
cp .env.example .env
```

Edit `.env` and set:
- `LINKEDIN_CLIENT_ID` - Your LinkedIn OAuth app client ID
- `LINKEDIN_CLIENT_SECRET` - Your LinkedIn OAuth app client secret
- `OPENAI_API_KEY` - Your OpenAI API key
- `JWT_SECRET_KEY` - Generate with: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
- `DATABASE_URL` - Keep default for local development
- `REDIS_URL` - Keep default for local development

### 3. Run Database Migrations

Apply the database schema:

```bash
cd backend
uv run alembic upgrade head
```

This creates:
- Users table
- Groups table
- UserGroups association table
- Default 'user' group

### 4. Start Backend and Frontend

```bash
# Start backend
docker-compose up -d backend

# Start frontend
docker-compose up -d frontend
```

## Admin User Management

### Creating Admin Users

To create an admin user, you need to manually assign the 'admin' group:

1. First, create the admin group (if it doesn't exist):
```sql
INSERT INTO groups (name, description) VALUES ('admin', 'Administrator group');
```

2. Find the user ID:
```sql
SELECT id, email FROM users;
```

3. Assign the admin group:
```sql
INSERT INTO user_groups (user_id, group_id)
SELECT <user_id>, id FROM groups WHERE name = 'admin';
```

Or use the admin API endpoints (if you already have an admin user):
```bash
# Create admin group
curl -X POST http://localhost:8000/api/admin/groups \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "admin", "description": "Administrator group"}'

# Assign admin group to user
curl -X POST http://localhost:8000/api/admin/users/1/groups \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1, "group_name": "admin"}'
```

## API Endpoints

### Public Endpoints
- `POST /api/auth/token` - Exchange LinkedIn code for custom tokens
- `POST /api/auth/refresh` - Refresh access token

### Protected Endpoints (Require Authentication)
- `GET /api/me` - Get current user info
- `POST /api/chat` - Send chat message

### Admin Endpoints (Require 'admin' Scope)
- `POST /api/admin/groups` - Create new group
- `GET /api/admin/groups` - List all groups
- `GET /api/admin/users` - List all users with groups
- `POST /api/admin/users/{user_id}/groups` - Assign group to user
- `DELETE /api/admin/users/{user_id}/groups/{group_name}` - Remove group from user

## Token Management

### Manual Token Validation

You can validate tokens using:

```bash
# Check if a token is cached in Redis
redis-cli get "access_token:TOKEN_ID"

# Check refresh token
redis-cli get "refresh_token:TOKEN_ID"
```

### Revoking Tokens

Tokens can be revoked by deleting them from Redis:

```bash
# Revoke access token
redis-cli del "access_token:TOKEN_ID"

# Revoke refresh token
redis-cli del "refresh_token:TOKEN_ID"
```

## Development vs Production

### Local Development
- Use Docker Compose for PostgreSQL and Redis
- Database and Redis run alongside the application

### Production (AWS Deployment)
- Use AWS RDS for PostgreSQL (managed database)
- Use AWS ElastiCache for Redis (managed cache)
- Remove `depends_on` for postgres/redis in docker-compose.yml
- Update `DATABASE_URL` and `REDIS_URL` to point to AWS services

## Troubleshooting

### Database Connection Issues

```bash
# Check if PostgreSQL is running
docker-compose ps postgres

# Check PostgreSQL logs
docker-compose logs postgres

# Test connection
docker-compose exec postgres psql -U chatbot_user -d chatbot -c "SELECT 1;"
```

### Redis Connection Issues

```bash
# Check if Redis is running
docker-compose ps redis

# Check Redis logs
docker-compose logs redis

# Test connection
docker-compose exec redis redis-cli ping
```

### Migration Issues

```bash
# Check current migration version
cd backend
uv run alembic current

# View migration history
uv run alembic history

# Rollback migration
uv run alembic downgrade -1

# Reapply migration
uv run alembic upgrade head
```

## Security Considerations

1. **JWT Secret Key**: Use a strong, randomly generated secret key in production
2. **Database Credentials**: Change default PostgreSQL password in production
3. **Redis Security**: Enable Redis authentication in production
4. **HTTPS**: Use HTTPS in production for secure token transmission
5. **Token Storage**: Tokens are stored in localStorage (consider HttpOnly cookies for enhanced security)
6. **Rate Limiting**: Consider adding rate limiting to prevent abuse
