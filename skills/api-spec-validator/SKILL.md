---
name: api-spec-validator
description: Validate FastAPI and REST API endpoints against OpenAPI schemas, HTTP semantics, and Pydantic model contracts.
version: 1.0.0
tags: [api, fastapi, rest, validation, openapi, schema, contract]
---

# Procedural Knowledge: API & Route Specification Validation

When developing, refactoring, or auditing FastAPI / REST API endpoints:

## Phase 1: Route Discovery & Static Linting
1. Execute the route linter helper script:
   `python skills/api-spec-validator/scripts/route_linter.py <target_directory_or_file>`
2. Check for missing `response_model`, non-standard status codes, or unannotated path parameters.

## Phase 2: HTTP Verb Semantics Verification
1. `GET`: Safe, idempotent, must not mutate state.
2. `POST`: Resource creation or non-idempotent operations, returns `201 Created` or `200 OK`.
3. `PUT` / `PATCH`: Idempotent or partial update, returns `200 OK` or `204 No Content`.
4. `DELETE`: Resource deletion, returns `200 OK` or `204 No Content`.

## Phase 3: Pydantic Schema & Contract Integrity
1. Ensure request body models have `Field` descriptions, examples, and validation bounds.
2. Check that error responses adhere to standard JSON error envelope format (`{"detail": "..."}` or `{"error": {"code": ...}}`).

## Phase 4: Integration Verification
1. Run endpoint tests using `TestClient` or `httpx.AsyncClient`.
2. Verify that 422 Unprocessable Entity is properly raised for invalid inputs.

## Phase 5: Deliverables
1. List of validated routes and compliance score.
2. Recommended refactors for any schema or status code discrepancies.
