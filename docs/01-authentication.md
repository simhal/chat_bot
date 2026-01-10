# Authentication

## Overview

The platform uses **LinkedIn OAuth 2.0** for identity verification combined with **platform-issued JWT tokens** for API access. This approach leverages LinkedIn's trusted identity while maintaining full control over session management and token lifecycle.

---

## Authentication Flow

### Sequence Diagram

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Browser   │     │  Frontend   │     │   Backend   │     │  LinkedIn   │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │                   │
       │ 1. Click Login    │                   │                   │
       │──────────────────>│                   │                   │
       │                   │                   │                   │
       │ 2. Redirect to LinkedIn              │                   │
       │<──────────────────│                   │                   │
       │                   │                   │                   │
       │ 3. User authenticates with LinkedIn  │                   │
       │───────────────────────────────────────────────────────────>
       │                   │                   │                   │
       │ 4. LinkedIn returns authorization code                   │
       │<───────────────────────────────────────────────────────────
       │                   │                   │                   │
       │ 5. Frontend sends code to backend    │                   │
       │──────────────────────────────────────>│                   │
       │                   │                   │                   │
       │                   │                   │ 6. Exchange code  │
       │                   │                   │    for ID token   │
       │                   │                   │──────────────────>│
       │                   │                   │<──────────────────│
       │                   │                   │                   │
       │                   │                   │ 7. Validate token,
       │                   │                   │    create user,
       │                   │                   │    generate JWT,
       │                   │                   │    register in Redis
       │                   │                   │                   │
       │ 8. Return platform tokens            │                   │
       │<──────────────────────────────────────│                   │
       │                   │                   │                   │
       │ 9. Store tokens, establish session   │                   │
       └───────────────────┴───────────────────┴───────────────────┘
```

### Step-by-Step

1. **User initiates login** - Clicks LinkedIn login button
2. **Redirect to LinkedIn** - Browser redirected to LinkedIn OAuth page
3. **User authenticates** - Enters LinkedIn credentials on LinkedIn's site
4. **Authorization code returned** - LinkedIn redirects back with temporary code
5. **Code sent to backend** - Frontend posts code to `/api/auth/callback`
6. **Token exchange** - Backend exchanges code for LinkedIn ID token
7. **User processing** - Backend validates token, creates/updates user, generates JWT
8. **Tokens returned** - Platform access and refresh tokens sent to frontend
9. **Session established** - Frontend stores tokens for API calls

---

## LinkedIn OAuth Integration

### Why LinkedIn?

- **Professional identity** - Users verified through professional profiles
- **No password management** - Platform doesn't store passwords
- **Single sign-on** - Seamless access for logged-in LinkedIn users
- **Rich profile data** - Name, email, photo provided automatically

### OAuth Scopes Requested

| Scope | Purpose | Data Received |
|-------|---------|---------------|
| `openid` | OpenID Connect protocol | Unique user identifier |
| `profile` | Basic profile info | Name, profile photo |
| `email` | Email address | Primary email |

### Token Validation

LinkedIn ID tokens are validated using:
- **JWKS (JSON Web Key Set)** - LinkedIn's public keys verify signature
- **Standard claims** - `iss`, `aud`, `exp` validated per OIDC spec
- **Email verification** - Only verified emails accepted

---

## Platform Token System

### Why Platform Tokens?

LinkedIn tokens are exchanged for platform-issued tokens because:

1. **Custom claims** - Platform roles and permissions embedded
2. **Controlled lifecycle** - Expiration managed independently
3. **Fast validation** - No external API calls needed
4. **Revocation support** - Tokens can be invalidated instantly

### Token Types

| Token | Purpose | Lifetime | Storage |
|-------|---------|----------|---------|
| **Access Token** | API authentication | 1 hour | Memory (Svelte store) |
| **Refresh Token** | Obtain new access tokens | 7 days | HttpOnly cookie (optional) |

### Access Token Structure (JWT)

```json
{
  "sub": "user-uuid-123",
  "email": "user@example.com",
  "name": "John",
  "surname": "Doe",
  "scopes": ["macro:analyst", "equity:reader"],
  "jti": "token-id-456",
  "iat": 1704063600,
  "exp": 1704067200
}
```

| Claim | Description |
|-------|-------------|
| `sub` | User's unique identifier |
| `email` | User's email address |
| `name` / `surname` | Display name |
| `scopes` | Permission scopes (see [Authorization](./02-authorization_concept.md)) |
| `jti` | Token ID for revocation lookup |
| `iat` | Issued at timestamp |
| `exp` | Expiration timestamp |

---

## Token Validation Flow

Every API request is validated:

```
API Request with Authorization Header
                │
                ▼
┌───────────────────────────────┐
│ 1. Extract Bearer Token       │
└───────────────┬───────────────┘
                │
                ▼
┌───────────────────────────────┐
│ 2. Decode & Verify JWT        │
│    - Valid signature?         │
│    - Not expired?             │
│    - Valid structure?         │
└───────────────┬───────────────┘
                │
                ▼
┌───────────────────────────────┐
│ 3. Check Redis Token Registry │
│    - Token ID (jti) exists?   │
│    - Enables revocation       │
└───────────────┬───────────────┘
                │
       ┌────────┴────────┐
      Valid           Invalid
       │                 │
       ▼                 ▼
    Process           Reject
    Request          (401)
```

---

## Token Revocation

### Redis Token Registry

JWT tokens are stateless - once issued, they're valid until expiration. The **Redis token registry** solves this:

- Token ID registered in Redis on creation
- Validation checks Redis for token ID
- Deleting token ID instantly invalidates token
- Redis TTL auto-expires entries

### Revocation Scenarios

| Scenario | Action | Scope |
|----------|--------|-------|
| User logout | Delete token ID | Single token |
| Security concern | Delete all user's tokens | All sessions |
| Account deactivation | Delete tokens + mark inactive | All sessions |
| Admin action | Revoke specific session | Single token |

### Revocation Process

```
Logout Request
      │
      ▼
┌─────────────────────────┐
│ DELETE from Redis       │
│ Key: access_token:{jti} │
└─────────────────────────┘
      │
      ▼
Future requests with token
      │
      ▼
┌─────────────────────────┐
│ Redis lookup fails      │
│ → 401 Unauthorized      │
└─────────────────────────┘
```

---

## Token Refresh

When access token expires:

1. Frontend detects 401 response
2. Sends refresh token to `/api/auth/refresh`
3. Backend validates refresh token
4. New access token issued
5. Frontend retries original request

```
┌──────────────────────────────────────────────────────────┐
│ Access Token Expired                                      │
│                                                          │
│  Frontend                      Backend                   │
│     │                            │                       │
│     │ POST /api/auth/refresh     │                       │
│     │ (with refresh token)       │                       │
│     │ ─────────────────────────► │                       │
│     │                            │                       │
│     │                            │ Validate refresh     │
│     │                            │ token, issue new     │
│     │                            │ access token         │
│     │                            │                       │
│     │ ◄───────────────────────── │                       │
│     │ (new access token)         │                       │
│     │                            │                       │
│     │ Retry original request     │                       │
│     │ ─────────────────────────► │                       │
└──────────────────────────────────────────────────────────┘
```

---

## Security Considerations

### Token Storage

| Token | Storage | Protection |
|-------|---------|------------|
| Access Token | Memory (Svelte store) | Cleared on page close, not in localStorage |
| Refresh Token | HttpOnly cookie | Protected from XSS |

### CORS Protection

- Only configured frontend origins allowed
- Credentials require explicit CORS permission
- Prevents cross-site authenticated requests

### Security Properties

| Property | Implementation |
|----------|----------------|
| Integrity | JWT signature prevents tampering |
| Confidentiality | HTTPS encrypts tokens in transit |
| Expiration | Short-lived tokens limit exposure |
| Revocation | Redis registry enables instant invalidation |

---

## Error Responses

| Error | HTTP Status | Meaning | Action |
|-------|-------------|---------|--------|
| Missing token | 401 | No Authorization header | Login required |
| Invalid token | 401 | JWT validation failed | Re-authenticate |
| Expired token | 401 | Token past expiration | Refresh or re-login |
| Revoked token | 401 | Token ID not in Redis | Re-authenticate |
| User inactive | 401 | Account deactivated | Contact admin |

---

## Related Documentation

- [Authorization](./02-authorization_concept.md) - Permission system and role hierarchy
- [User Management](./04-user-management.md) - User accounts and groups
- [Redis Cache](./12-redis-cache.md) - Token registry implementation
