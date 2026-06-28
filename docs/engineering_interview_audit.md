# Engineering Interview Audit

> Audit of Docker, Memory/Cache, and LLM failure handling for interview readiness.
> All statements based on actual code, not production claims.

---

## 1. Docker / Compose Audit

### docker-compose.yml Structure

```yaml
services:
  codepilot:
    build: .                    # Builds from Dockerfile
    ports:
      - "8000:8000"            # Host:Container port mapping
    env_file:
      - .env                    # Injects CODEPILOT_* env vars
    volumes:
      - ./workspace:/app/workspace  # Mounts local workspace into container
    environment:
      - CODEPILOT_WORKSPACE_ROOT=/app/workspace  # Overrides workspace path
    healthcheck:
      test: ["CMD", "python", "-c", "import httpx; httpx.get('http://localhost:8000/health')"]
      interval: 10s
      timeout: 5s
      retries: 3
```

### Q&A: Docker Operations

**Q: What does `docker compose up -d --build` do?**
1. Builds image from Dockerfile (python:3.11-slim base, pip install, copy app code)
2. Creates container with port 8000 mapped, .env injected, workspace volume mounted
3. Starts in detached mode (`-d`)
4. Healthcheck polls `/health` every 10s

**Q: How to debug with `docker compose logs -f api`?**
- `-f` follows log output in real-time
- Shows uvicorn startup logs, request logs, exception traces
- Filter by service name: `docker compose logs -f codepilot`

**Q: What does `docker compose ps` show?**
- Container status (running/exited/healthy/unhealthy)
- Port mappings
- Volume mounts

**Q: `docker compose down` vs `restart`?**
- `down`: stops and removes container + network (clean slate)
- `restart`: stops and starts same container (preserves state)

**Q: How are environment variables injected?**
- `.env` file → `env_file:` directive → container environment
- Prefix `CODEPILOT_` maps to `Settings` fields via pydantic-settings
- Example: `CODEPILOT_LLM_API_KEY` → `settings.llm_api_key`

**Q: Port mapping?**
- Host 8000 → Container 8000
- Change host port: `ports: "9000:8000"`

**Q: Volume mounts?**
- `./workspace:/app/workspace` — mounts local workspace into container
- User uploads persist on host, survive container restarts
- `data/` directory NOT mounted by default (memory persistence in-container only)

**Q: Container startup failure diagnosis order?**
1. `docker compose logs codepilot` — check startup errors
2. `.env` — verify API key and config
3. `docker compose ps` — check health status
4. Port conflict — another process on 8000?
5. Volume path — does `./workspace` exist on host?

### Dockerfile Analysis

```dockerfile
FROM python:3.11-slim          # Lightweight base
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir # No cache in image
COPY app/ workspace/ evaluation/ scripts/  # App code
RUN mkdir -p workspace/uploads # Creates upload directory
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- Base image: `python:3.11-slim` (~150MB, not alpine for numpy/FAISS compat)
- `--no-cache-dir`: smaller image size
- Volume mount overrides `workspace/` at runtime
- Healthcheck uses httpx (already a dependency)

---

## 2. Memory / Cache Degradation

### Architecture Principle

Memory and cache are **enhancement layers**, not hard dependencies.
If they fail, the agent continues with degraded (but functional) behavior.

### Failure Modes

| Component | Failure | Behavior | Service Impact |
|-----------|---------|----------|---------------|
| Memory JSON missing | First startup, no data/memory/ | `_load()` returns empty, normal startup | None |
| Memory JSON corrupted | Invalid JSON in file | `logger.warning`, fallback empty memory | None |
| Memory write fails | Disk full, permission denied | `logger.warning`, in-memory continues | None |
| Index cache miss | First request or TTL expired | `IndexBuilder().build()` called, result cached | Slight delay (~100ms) |
| Index cache corrupted | Unexpected data | Cache miss, rebuild from scratch | None |
| Embedding model unavailable | sentence-transformers not installed | `_model_failed=True`, embedding layer skipped | Rule-based routing still works |

### Key Code Paths

**Memory load on startup:**
```python
# memory_store.py
def _load(self):
    if not self._persist_path or not self._persist_path.exists():
        return  # File missing → empty memory, no error
    try:
        data = json.loads(self._persist_path.read_text())
        # ... load tasks, errors, repos
    except (json.JSONDecodeError, TypeError, KeyError) as exc:
        logger.warning("Failed to load memory file, starting fresh: %s", exc)
        self._tasks = []  # Fallback to empty
```

**Index cache TTL:**
```python
# index_cache.py
def get(self, workspace_root):
    entry = self._cache.get(workspace_root)
    if entry is None:
        return None  # Cache miss → rebuild
    ts, index = entry
    if time.monotonic() - ts > self._ttl:
        del self._cache[workspace_root]  # Expired → rebuild
        return None
    return index
```

### Interview Answer: "What if memory fails?"

> Memory is an enhancement layer. If the JSON file is missing or corrupted, the agent starts with empty memory and functions normally. The `_load()` method catches `JSONDecodeError` and logs a warning. In-memory storage always works as fallback. The agent's core ReAct loop doesn't depend on memory — it's injected as additional context in the system prompt.

---

## 3. LLM Failure Handling

### Configuration (config.py)

```python
llm_timeout_seconds: int = 30        # HTTP timeout
llm_max_retries: int = 2             # Retry attempts
llm_retry_backoff_seconds: float = 1.0  # Base backoff
```

### Retry Logic (llm_client.py)

| Error Type | Retry? | Behavior |
|-----------|--------|----------|
| `httpx.TimeoutException` | Yes | Exponential backoff: `1s, 2s` |
| `httpx.ConnectError` | Yes | Same backoff |
| HTTP 429 (rate limit) | Yes | Uses `Retry-After` header, or 2s |
| HTTP 5xx (server error) | Yes | Exponential backoff |
| HTTP 400 (bad request) | **No** | Logs error, raises `LLMClientError` |
| Auth error / invalid key | **No** | Logs error, raises `LLMClientError` |
| Final failure | — | `LLMClientError` with retry count and last exception |

### Key Code Path

```python
# llm_client.py
async def _send_request(self, payload):
    for attempt in range(1, self._max_retries + 1):
        try:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 2))
                await asyncio.sleep(retry_after)
                continue
            if resp.status_code >= 500:
                await asyncio.sleep(self._retry_backoff * attempt)
                continue
            if resp.status_code >= 400:
                logger.error("LLM API error %d: %s", resp.status_code, body)
            resp.raise_for_status()
            return resp.json()
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            last_exc = exc
            if attempt < self._max_retries:
                await asyncio.sleep(self._retry_backoff * attempt)
    raise LLMClientError(f"LLM 调用失败，已重试 {self._max_retries} 次: {last_exc}")
```

### Interview Answers

**Q: "LLM API 超时怎么办？"**
> 每次请求有 30s 超时（可配置）。超时后自动重试，最多 2 次，退避间隔 1s、2s。重试时记录 warning 日志。最终失败抛出 `LLMClientError`，不会静默失败。

**Q: "DeepSeek 429 怎么办？"**
> 429 是 rate limit。读取 `Retry-After` header 等待指定时间后重试。如果 header 不存在，默认等 2s。同样最多重试 2 次。

**Q: "鉴权失败为什么不重试？"**
> 400/401/403 是客户端错误，重试不会改变结果。API key 无效重试 100 次还是无效。所以直接抛出异常，让调用方决定下一步（检查配置、通知用户）。

**Q: "React agent 怎么处理 LLM 失败？"**
> D34 之后，`react_agent.py` 中所有 `except Exception` 都记录异常类型和消息。LLM 调用失败会向上传播 `LLMClientError`，API 层返回 500 + 错误信息。不会静默变成空回答。

---

## 4. Configuration Summary

All configurable values with defaults:

| Setting | Default | Where Used |
|---------|---------|-----------|
| `llm_timeout_seconds` | 30 | LLM HTTP timeout |
| `llm_max_retries` | 2 | LLM retry count |
| `llm_retry_backoff_seconds` | 1.0 | LLM retry backoff |
| `max_tool_calls` | 20 | Agent budget |
| `command_timeout` | 60 | pytest execution timeout |
| `intent_embedding_threshold` | 0.55 | Embedding router confidence |
| `workspace_index_cache_ttl` | 300 | Index cache TTL (seconds) |
| `execution_mode` | "local" | local or docker |
