# RESTful API Design & FastAPI Best Practices

A quick reference guide for designing and maintaining robust RESTful APIs in FastAPI.

---

## 1. HTTP Status Code Guidelines

| Code | Status | Usage Scenario |
|---|---|---|
| **200** | OK | Standard successful response for GET, PUT, PATCH. |
| **201** | Created | Resource successfully created via POST. |
| **204** | No Content | Successful operation returning no body (e.g. DELETE). |
| **400** | Bad Request | Client-side invalid parameters or domain validation failure. |
| **401** | Unauthorized | Missing or invalid authentication token. |
| **403** | Forbidden | Authenticated user lacks permission to access resource. |
| **404** | Not Found | Target resource does not exist. |
| **422** | Unprocessable Entity | Pydantic schema validation error on input payload. |
| **500** | Internal Server Error | Unhandled backend exception or system failure. |

---

## 2. Pydantic Model Schema Conventions

1. **Request Models**: Suffix with `Request` or `Create` / `Update` (e.g., `ChatRequest`, `FileCreate`).
2. **Response Models**: Suffix with `Response` or `Out` (e.g., `ChatResponse`, `ToolMetadataOut`).
3. **Field Annotations**: Always provide default values or `Field(..., description="...")` to generate clean OpenAPI Swagger documentation.
