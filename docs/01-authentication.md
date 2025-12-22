# Authentication & Authorization

## Overview

The platform uses a **dual-layer security system** combining enterprise identity verification with session management. Users authenticate through LinkedIn OAuth 2.0 (providing trusted identity), while the platform issues its own tokens for API access control. Authorization is enforced through a role-based access control (RBAC) system where permissions are encoded directly in tokens.

---

## Why This Approach?

### The Challenge

Enterprise applications need to solve two distinct problems:

1. **Identity**: "Who is this user?" - Verifying someone is who they claim to be
2. **Authorization**: "What can they do?" - Determining what actions they're permitted to perform

Using LinkedIn OAuth alone would require calling LinkedIn on every API request (slow, expensive, dependent on external service). Using only internal passwords would mean managing credential security, password resets, and account recovery.

### The Solution

The platform combines the best of both approaches:

- **LinkedIn OAuth** handles identity verification (users prove who they are)
- **Internal JWT tokens** handle session management (fast, stateless API authentication)
- **Redis token registry** enables instant revocation (security without sacrificing speed)

---

## Authentication Flow

The complete login process involves four parties working together:

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Browser   │     │  Frontend   │     │   Backend   │     │  LinkedIn   │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │                   │
       │ 1. User clicks    │                   │                   │
       │    "Login"        │                   │                   │
       │──────────────────>│                   │                   │
       │                   │                   │                   │
       │ 2. Redirect to    │                   │                   │
       │    LinkedIn       │                   │                   │
       │<──────────────────│                   │                   │
       │                   │                   │                   │
       │ 3. User enters LinkedIn credentials   │                   │
       │───────────────────────────────────────────────────────────>
       │                   │                   │                   │
       │ 4. LinkedIn verifies & returns code   │                   │
       │<───────────────────────────────────────────────────────────
       │                   │                   │                   │
       │ 5. Frontend sends code to backend     │                   │
       │──────────────────────────────────────>│                   │
       │                   │                   │                   │
       │                   │                   │ 6. Backend exchanges
       │                   │                   │    code for ID token
       │                   │                   │──────────────────>│
       │                   │                   │<──────────────────│
       │                   │                   │                   │
       │                   │                   │ 7. Validate token,
       │                   │                   │    create/update user,
       │                   │                   │    generate JWT,
       │                   │                   │    cache in Redis
       │                   │                   │                   │
       │ 8. Return platform tokens             │                   │
       │<──────────────────────────────────────│                   │
       │                   │                   │                   │
       │ 9. Store tokens   │                   │                   │
       │   & start session │                   │                   │
       └───────────────────┴───────────────────┴───────────────────┘
```

### Step-by-Step Explanation

1. **User initiates login**: Clicks the LinkedIn login button on the frontend
2. **Redirect to LinkedIn**: Browser is sent to LinkedIn's authorization page
3. **User authenticates**: User enters their LinkedIn credentials directly on LinkedIn's site
4. **Authorization code returned**: LinkedIn redirects back with a temporary authorization code
5. **Code exchange**: Frontend sends this code to the backend
6. **Token exchange**: Backend securely exchanges the code for LinkedIn's ID token
7. **User processing**: Backend validates the token, creates or updates the user record, generates platform tokens, and registers them in Redis
8. **Tokens returned**: Platform access and refresh tokens are sent to the frontend
9. **Session established**: Frontend stores tokens and user gains access

---

## LinkedIn OAuth Integration

### Why LinkedIn?

LinkedIn provides several advantages for enterprise authentication:

- **Professional identity**: Users are verified through their professional profiles
- **No password management**: The platform doesn't store user passwords
- **Single sign-on**: Users who are already logged into LinkedIn get seamless access
- **Rich profile data**: Name, email, and profile photo are provided automatically

### OAuth Scopes

The platform requests specific permissions from LinkedIn:

| Scope | Purpose | Data Received |
|-------|---------|---------------|
| `openid` | Enable OpenID Connect protocol | Unique user identifier |
| `profile` | Access basic profile information | Name, profile photo |
| `email` | Access email address | Primary email |

### OpenID Connect

LinkedIn uses OpenID Connect, which provides:

- **ID Token**: A cryptographically signed statement of the user's identity
- **JWKS Validation**: Tokens are verified using LinkedIn's public keys
- **Standard Claims**: Consistent format for user information across providers

---

## Token System

### Why Custom Tokens?

While LinkedIn provides an ID token, the platform generates its own tokens because:

1. **Custom claims**: Platform-specific data (roles, permissions) can be embedded
2. **Independent lifecycle**: Token expiration is controlled by the platform, not LinkedIn
3. **Revocation capability**: Tokens can be invalidated without involving LinkedIn
4. **Reduced latency**: No external API calls needed for each request

### Token Types

The platform uses two token types working together:

| Token | Purpose | Lifetime | Usage |
|-------|---------|----------|-------|
| **Access Token** | Authenticate API requests | Short (hours) | Sent with every API call |
| **Refresh Token** | Obtain new access tokens | Long (days) | Used only to get new access tokens |

### Access Token Contents

Access tokens are self-contained, carrying all necessary information for authorization:

| Claim | Description |
|-------|-------------|
| **Subject (sub)** | User's unique identifier |
| **Email** | User's email address |
| **Name/Surname** | User's display name |
| **Scopes** | Array of group memberships (permissions) |
| **Token ID (jti)** | Unique identifier for revocation lookup |
| **Expiration (exp)** | When the token becomes invalid |
| **Issued At (iat)** | When the token was created |

### Token Validation Flow

Every API request goes through this validation process:

```
API Request with Token
         │
         ▼
┌─────────────────────────────┐
│ 1. Decode JWT               │
│    - Verify signature       │
│    - Check expiration       │
│    - Validate structure     │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│ 2. Check Redis Registry     │
│    - Token ID must exist    │
│    - Enables revocation     │
└─────────────┬───────────────┘
              │
     Token valid?
    ┌────┴────┐
   Yes        No
    │          │
    ▼          ▼
 Process    Reject
 Request    (401)
```

### Why Redis for Token Registry?

JWT tokens are stateless by design - once issued, they're valid until expiration. This creates a problem: how do you invalidate a token before it expires (e.g., on logout or security breach)?

The solution is a **token registry** in Redis:

- When a token is created, its ID is registered in Redis
- During validation, the token ID must exist in Redis
- To revoke a token, simply delete its ID from Redis
- Redis's sub-millisecond lookups add negligible latency

---

## Authorization System

### The Scope Model

Permissions are encoded as **scopes** in the format `{groupname}:{role}`:

```
Examples:
  global:admin     → System-wide administrator
  macro:analyst    → Macroeconomic content creator
  equity:editor    → Equity content reviewer
  fixed_income:reader → Fixed income read-only access
```

### Permission Hierarchy

The authorization system follows a hierarchical model where higher roles inherit lower role permissions:

```
┌─────────────────────────────────────────────────────────────┐
│                      global:admin                            │
│        (Bypasses all permission checks - full access)        │
└──────────────────────────────┬──────────────────────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
    ┌───────────┐        ┌───────────┐        ┌───────────┐
    │{topic}:   │        │{topic}:   │        │{topic}:   │
    │  admin    │        │  admin    │        │  admin    │
    │           │        │           │        │           │
    │Full topic │        │Full topic │        │Full topic │
    │control    │        │control    │        │control    │
    └─────┬─────┘        └─────┬─────┘        └─────┬─────┘
          │                    │                    │
          ▼                    ▼                    ▼
    ┌───────────┐        ┌───────────┐        ┌───────────┐
    │{topic}:   │        │{topic}:   │        │{topic}:   │
    │  analyst  │        │  analyst  │        │  analyst  │
    │           │        │           │        │           │
    │Create &   │        │Create &   │        │Create &   │
    │edit drafts│        │edit drafts│        │edit drafts│
    └─────┬─────┘        └─────┬─────┘        └─────┬─────┘
          │                    │                    │
          ▼                    ▼                    ▼
    ┌───────────┐        ┌───────────┐        ┌───────────┐
    │{topic}:   │        │{topic}:   │        │{topic}:   │
    │  editor   │        │  editor   │        │  editor   │
    │           │        │           │        │           │
    │Review &   │        │Review &   │        │Review &   │
    │publish    │        │publish    │        │publish    │
    └─────┬─────┘        └─────┬─────┘        └─────┬─────┘
          │                    │                    │
          ▼                    ▼                    ▼
    ┌───────────┐        ┌───────────┐        ┌───────────┐
    │{topic}:   │        │{topic}:   │        │{topic}:   │
    │  reader   │        │  reader   │        │  reader   │
    │           │        │           │        │           │
    │View       │        │View       │        │View       │
    │published  │        │published  │        │published  │
    └───────────┘        └───────────┘        └───────────┘
```

### Permission Check Logic

When a protected endpoint is accessed, the system checks permissions in order:

1. **Global admin bypass**: If user has `global:admin` scope, access is granted immediately
2. **Topic admin check**: If user has `{topic}:admin`, access is granted for that topic
3. **Role-specific check**: User must have the required role for the specific topic
4. **Denial**: If no matching scope is found, request is rejected with 403 Forbidden

### Role Capabilities Summary

| Role | View Published | View Drafts | Create | Edit Own | Edit Others | Publish | Manage Users |
|------|----------------|-------------|--------|----------|-------------|---------|--------------|
| `reader` | Yes | No | No | No | No | No | No |
| `editor` | Yes | Yes | No | No | Yes (in review) | Yes | No |
| `analyst` | Yes | Yes | Yes | Yes | No | No | No |
| `admin` | Yes | Yes | Yes | Yes | Yes | Yes | Topic only |
| `global:admin` | Yes | Yes | Yes | Yes | Yes | Yes | All |

---

## Token Revocation

### Revocation Scenarios

Tokens may need to be invalidated before their natural expiration:

| Scenario | Action | Scope |
|----------|--------|-------|
| **User logout** | Delete token ID from Redis | Single token |
| **Password change** | (Not applicable - OAuth) | - |
| **Security concern** | Delete all user's tokens | All user tokens |
| **Account deactivation** | Delete tokens + mark user inactive | All user tokens |
| **Admin action** | Revoke specific session | Single token |

### Revocation Process

```
Revocation Request
        │
        ▼
┌───────────────────────────────┐
│ Delete token ID from Redis    │
│                               │
│ Key: access_token:{token_id}  │
│ Action: DELETE                │
└───────────────────────────────┘
        │
        ▼
Future requests with this token
        │
        ▼
┌───────────────────────────────┐
│ Token ID lookup fails         │
│                               │
│ Redis returns: null           │
│ Result: 401 Unauthorized      │
└───────────────────────────────┘
```

### Automatic Expiration

Tokens have built-in expiration through two mechanisms:

1. **JWT Expiration Claim**: The `exp` claim makes the token cryptographically invalid after the specified time
2. **Redis TTL**: The token registry entry automatically expires, matching the token lifetime

---

## Security Considerations

### Token Storage on Client

The frontend handles tokens carefully:

| Token Type | Storage Location | Reason |
|------------|------------------|--------|
| Access Token | Memory (Svelte store) | Cleared on page close, not accessible to XSS via storage |
| Refresh Token | HttpOnly cookie (optional) | Protected from JavaScript access |

### CORS Protection

Cross-Origin Resource Sharing (CORS) restricts which domains can call the API:

- Only configured frontend origins are allowed
- Credentials (cookies, auth headers) require explicit CORS permission
- Prevents malicious sites from making authenticated requests

### Token Security Properties

| Property | How It's Achieved |
|----------|-------------------|
| **Integrity** | JWT signature prevents tampering |
| **Confidentiality** | HTTPS encrypts tokens in transit |
| **Expiration** | Short-lived tokens limit exposure window |
| **Revocation** | Redis registry enables instant invalidation |
| **Non-replayability** | Unique token IDs prevent reuse after revocation |

---

## Error Responses

| Error | HTTP Status | Meaning | User Action |
|-------|-------------|---------|-------------|
| Invalid or expired token | 401 | JWT validation failed | Re-authenticate |
| Token revoked | 401 | Token ID not in Redis | Re-authenticate |
| Admin access required | 403 | User lacks admin scope | Contact administrator |
| Analyst access required | 403 | User lacks topic permission | Request access |
| User deactivated | 401 | Account has been disabled | Contact administrator |

---

## Integration Points

| Component | Authentication Role |
|-----------|---------------------|
| **Frontend Auth Store** | Stores tokens, tracks login state, provides user info to components |
| **API Client** | Attaches access token to every API request |
| **Backend Middleware** | Validates tokens on protected endpoints |
| **Redis Cache** | Token registry for revocation support |
| **PostgreSQL** | User records, group memberships, audit logs |
