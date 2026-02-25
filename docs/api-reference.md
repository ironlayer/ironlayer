# API Reference

The IronLayer API is a FastAPI application running on port 8000 by default. Full interactive documentation is available at `/docs` (Swagger UI) and `/redoc` (ReDoc) when the server is running.

## Base URL

```
http://localhost:8000/api/v1
```

## Authentication

Authentication mode is controlled by `API_AUTH_MODE`:

### Dev Mode (`API_AUTH_MODE=dev`)

No authentication required. All requests are associated with a default tenant. Used by `ironlayer dev` for local development.

### JWT Mode (`API_AUTH_MODE=jwt`)

Pass a Bearer token in the `Authorization` header:

```bash
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/v1/plans
```

JWT tokens must contain:
- `sub` -- User identity
- `tenant_id` -- Tenant identifier (used for RLS)
- `role` -- User role (`viewer`, `operator`, `admin`)
- `jti` -- JWT ID (for replay protection)

Token signing uses the secret in `API_JWT_SECRET`.

### OIDC Mode (`API_AUTH_MODE=oidc`)

Tokens are validated against an external OpenID Connect provider. Configure:
- `API_OIDC_ISSUER` -- OIDC issuer URL
- `API_OIDC_AUDIENCE` -- Expected audience claim

## Rate Limiting

Enabled by default (`API_RATE_LIMIT_ENABLED=true`):

| Endpoint Type | Limit |
|---------------|-------|
| General endpoints | 60 requests/minute per tenant |
| Auth endpoints | 20 requests/minute per IP |
| Burst multiplier | 1.5x |

Rate limit headers are returned on all responses:
- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Reset`

Disabled automatically in local dev mode.

## Endpoints

### Health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/ready` | No | Readiness probe (returns `ready` when database is connected) |
| GET | `/health` | No | Health check |

### Plans

| Method | Path | Auth | Roles | Description |
|--------|------|------|-------|-------------|
| POST | `/api/v1/plans` | Yes | operator, admin | Create a new execution plan |
| GET | `/api/v1/plans` | Yes | All | List plans for the current tenant |
| GET | `/api/v1/plans/{plan_id}` | Yes | All | Retrieve a specific plan |

### Approvals

| Method | Path | Auth | Roles | Description |
|--------|------|------|-------|-------------|
| POST | `/api/v1/plans/{plan_id}/approve` | Yes | operator, admin | Approve a plan for execution |
| POST | `/api/v1/plans/{plan_id}/apply` | Yes | operator, admin | Execute an approved plan |

### Runs

| Method | Path | Auth | Roles | Description |
|--------|------|------|-------|-------------|
| GET | `/api/v1/runs` | Yes | All | List execution runs |
| GET | `/api/v1/runs/{run_id}` | Yes | All | Retrieve a specific run |

### Backfills

| Method | Path | Auth | Roles | Description |
|--------|------|------|-------|-------------|
| POST | `/api/v1/backfills` | Yes | operator, admin | Create a backfill job |
| GET | `/api/v1/backfills` | Yes | All | List backfill jobs |

### Models

| Method | Path | Auth | Roles | Description |
|--------|------|------|-------|-------------|
| GET | `/api/v1/models` | Yes | All | List registered models |
| GET | `/api/v1/models/{name}` | Yes | All | Retrieve a specific model |

### Audit

| Method | Path | Auth | Roles | Description |
|--------|------|------|-------|-------------|
| GET | `/api/v1/audit` | Yes | admin | Query audit log entries |

### Reconciliation

| Method | Path | Auth | Roles | Description |
|--------|------|------|-------|-------------|
| POST | `/api/v1/reconciliation/check` | Yes | admin | Trigger a reconciliation check |
| GET | `/api/v1/reconciliation` | Yes | admin | List reconciliation results |

### Tenant Configuration

| Method | Path | Auth | Roles | Description |
|--------|------|------|-------|-------------|
| GET | `/api/v1/tenant/config` | Yes | admin | Get tenant configuration |
| PUT | `/api/v1/tenant/config` | Yes | admin | Update tenant configuration |

### Auth

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/auth/token` | No | Generate a JWT token (dev mode) |
| POST | `/api/v1/auth/revoke` | Yes | Revoke a token |

## Error Responses

All errors follow a consistent format:

```json
{
  "detail": "Human-readable error message"
}
```

| Status Code | Meaning |
|-------------|---------|
| 400 | Bad request (invalid input) |
| 401 | Authentication required |
| 403 | Insufficient permissions |
| 404 | Resource not found |
| 409 | Conflict (e.g., duplicate plan ID) |
| 422 | Validation error (Pydantic) |
| 429 | Rate limit exceeded |
| 500 | Internal server error |

## CORS

Cross-origin requests are allowed from origins in `API_CORS_ORIGINS` (default: `http://localhost:3000`).

## OpenAPI Specification

The full OpenAPI 3.0 spec is available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Raw JSON: `http://localhost:8000/openapi.json`
