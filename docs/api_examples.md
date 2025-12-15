# API Examples

This document shows quick curl examples for the cloud and edge APIs.

## Authentication

Obtain a JWT token (this repo simulates JWT issuance). Use the token in the `Authorization: Bearer <token>` header for protected endpoints.

## Cloud: Sync a report

Request:

```bash
curl -X POST https://localhost:8443/api/sync \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "report_id": "rep-1234",
    "title": "Example",
    "content": "Report content",
    "classification": "CUI",
    "updated_at": "2025-12-01T12:00:00Z",
    "updated_by": "analyst-1"
  }'
```

Success response (200):

```json
{ "status": "ok", "report_id": "rep-1234" }
```

Validation error (400):

```json
{ "message": "Missing required field: report_id" }
```

Authentication error (401):

```json
{ "message": "Token expired" }
```

Rate limit (429):

```json
{ "message": "Rate limit exceeded: try again later" }
```

Server error (500):

```json
{ "message": "Database error: could not insert record" }
```

## Edge: Create a local report

```bash
curl -X POST http://edge.local:5000/api/reports \
  -H "Content-Type: application/json" \
  -d '{
    "report_id": "rep-1234",
    "title": "Example",
    "content": "Local content",
    "classification": "IL4",
    "updated_at": "2025-12-01T12:00:00Z",
    "updated_by": "analyst-1"
  }'
```

Response (201):

```json
{ "id": 42, "report_id": "rep-1234" }
```

## Get latest reports (cloud)

```bash
curl -H "Authorization: Bearer $JWT" https://localhost:8443/api/reports/latest
```

Response (200): Array of latest `Report` objects (see `docs/openapi.yaml` for schema).
