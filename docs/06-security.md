# Security

This document describes the security architecture and measures implemented in the platform to protect user data, prevent common web vulnerabilities, and ensure secure communications.

---

## Security Principles

The application follows security best practices aligned with industry standards:

| Principle | Implementation |
|-----------|----------------|
| **Defense in Depth** | Multiple layers of security controls at network, application, and data levels |
| **Least Privilege** | Components operate with minimal required permissions; role-based access control |
| **Secure by Default** | Security features enabled automatically; opt-out rather than opt-in |
| **Input Validation** | All user inputs validated and sanitized at API boundaries |
| **Fail Securely** | Error handling prevents information disclosure; secure fallback behaviors |

---

## Authentication Security

### OAuth 2.0 Integration

The platform uses LinkedIn OAuth 2.0 for authentication:

| Component | Security Measure |
|-----------|------------------|
| **ID Token Validation** | Tokens validated using LinkedIn JWKS (JSON Web Key Set) |
| **Token Signature** | RS256 algorithm with LinkedIn public keys |
| **Token Expiration** | Automatic expiration and refresh token rotation |
| **State Parameter** | CSRF protection during OAuth flow |

### JWT Token Security

| Feature | Implementation |
|---------|----------------|
| **Algorithm** | HS256 with secure secret key |
| **Expiration** | Short-lived access tokens with configurable TTL |
| **Token Registry** | Active tokens tracked in Redis for revocation |
| **Scope Encoding** | User permissions embedded in token claims |
| **Revocation** | Logout invalidates tokens via Redis registry |

### Session Management

- Tokens stored client-side in localStorage
- Server-side token validation on every request
- Automatic logout on token expiration
- Token refresh extends session without re-authentication

---

## Authorization Security

### Role-Based Access Control

All API endpoints enforce role-based permissions:

| Endpoint Pattern | Access Control |
|------------------|----------------|
| `/api/reader/*` | Any authenticated user |
| `/api/analyst/{topic}/*` | Users with `{topic}:analyst` scope |
| `/api/editor/{topic}/*` | Users with `{topic}:editor` scope |
| `/api/admin/*` | Users with `global:admin` scope |

### Permission Verification Flow

1. JWT token extracted from Authorization header
2. Token signature and expiration validated
3. Token checked against Redis registry (revocation check)
4. User scopes extracted from token claims
5. Endpoint-specific role requirements verified
6. Request denied with 403 if insufficient permissions

---

## HTTP Security Headers

The backend applies security headers to all responses via SecurityHeadersMiddleware:

| Header | Value | Purpose |
|--------|-------|---------|
| **X-Frame-Options** | `DENY` | Prevents clickjacking by blocking iframe embedding |
| **X-Content-Type-Options** | `nosniff` | Prevents MIME type sniffing attacks |
| **X-XSS-Protection** | `1; mode=block` | Enables browser XSS filter (legacy browsers) |
| **Strict-Transport-Security** | `max-age=31536000; includeSubDomains` | Enforces HTTPS for 1 year |
| **Referrer-Policy** | `strict-origin-when-cross-origin` | Controls referrer information leakage |
| **Content-Security-Policy** | `default-src 'none'; frame-ancestors 'none'` | Restricts resource loading |
| **Permissions-Policy** | Disables camera, microphone, geolocation, etc. | Restricts browser feature access |

### Special Cases

Public resource endpoints (`/api/r/*`) have modified policies to allow iframe embedding for article HTML rendering:
- `frame-ancestors` allows frontend origins
- `X-Frame-Options` removed to avoid CSP conflicts
- Styles and scripts allowed inline for article content

---

## CORS Configuration

Cross-Origin Resource Sharing is configured with strict policies:

| Setting | Value |
|---------|-------|
| **Allowed Origins** | Configured via `CORS_ORIGINS` environment variable |
| **Credentials** | Enabled for cookie/token transmission |
| **Methods** | GET, POST, PUT, PATCH, DELETE, OPTIONS |
| **Headers** | Authorization, Content-Type, Accept, X-Requested-With |

---

## Input Validation and Sanitization

### Backend Validation

| Layer | Mechanism |
|-------|-----------|
| **Request Validation** | Pydantic models validate all request bodies |
| **Type Checking** | Strict type validation for all parameters |
| **Size Limits** | Maximum request body and file upload sizes |
| **SQL Injection** | SQLAlchemy ORM with parameterized queries |
| **Path Traversal** | File paths validated and sanitized |

### Frontend Sanitization

| Component | Security Measure |
|-----------|------------------|
| **Markdown Rendering** | DOMPurify sanitizes all HTML output from marked.js |
| **User Content Display** | All user-generated content escaped before rendering |
| **URL Handling** | Links validated before navigation |

---

## Data Protection

### Data at Rest

| Data Type | Protection |
|-----------|------------|
| **Database** | PostgreSQL with encrypted connections |
| **File Storage** | Resources stored with content-addressable hashing |
| **Credentials** | Environment variables, never in source code |
| **API Keys** | Loaded from secure environment configuration |

### Data in Transit

| Channel | Protection |
|---------|------------|
| **API Communication** | TLS/HTTPS enforced via HSTS |
| **Database Connections** | SSL connections to PostgreSQL |
| **Redis Connections** | Secure Redis connections in production |
| **WebSocket** | WSS (WebSocket Secure) for real-time features |

---

## Secret Management

| Secret Type | Storage Method |
|-------------|----------------|
| **JWT Secret** | Environment variable (`JWT_SECRET`) |
| **OAuth Credentials** | Environment variables |
| **API Keys** | Environment variables (OpenAI, Google, etc.) |
| **Database Credentials** | Connection string in environment |

Secrets are never:
- Committed to source control
- Logged in application output
- Exposed in error messages
- Returned in API responses

---

## Error Handling

Secure error handling prevents information disclosure:

| Error Type | Response |
|------------|----------|
| **Authentication Failure** | Generic "Invalid credentials" message |
| **Authorization Failure** | "Insufficient permissions" without scope details |
| **Server Errors** | Generic error message; details logged server-side |
| **Validation Errors** | Field-level errors without internal structure exposure |

---

## Monitoring and Logging

| Aspect | Implementation |
|--------|----------------|
| **Access Logging** | All API requests logged with timestamps |
| **Authentication Events** | Login, logout, and token refresh tracked |
| **Error Logging** | Server errors logged with stack traces (internal only) |
| **Security Events** | Failed authentication attempts tracked |
| **Audit Trail** | User actions on content recorded with timestamps |

---

## Development Security Practices

| Practice | Implementation |
|----------|----------------|
| **Dependency Scanning** | Regular updates to address vulnerabilities |
| **Code Review** | Security-focused review for all changes |
| **Environment Separation** | Distinct development and production configurations |
| **Least Privilege** | Service accounts with minimal database permissions |

---

## Compliance Alignment

The security controls are designed to align with:

| Standard | Coverage |
|----------|----------|
| **OWASP ASVS** | Application Security Verification Standard guidelines |
| **OWASP Top 10** | Protection against common web vulnerabilities |
| **Security Headers** | OWASP Secure Headers Project recommendations |

---

## Related Documentation

- Authentication - OAuth flow and JWT token management
- Authorization - Role-based access control and scopes
- Databases - Data storage and encryption
- Redis Cache - Token registry and session management
