from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        env_prefix="CODEPILOT_",
        extra="ignore",
    )

    # --- LLM ---
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o"
    llm_max_tokens: int = 4096

    # --- Agent ---
    workspace_root: Path = Path("./workspace")
    max_tool_calls: int = 20
    command_timeout: int = 60

    # --- LLM Retry ---
    llm_timeout_seconds: int = 30
    llm_max_retries: int = 2
    llm_retry_backoff_seconds: float = 1.0

    # --- Embedding ---
    intent_embedding_threshold: float = 0.55

    # --- Workspace Index Cache ---
    workspace_index_cache_ttl: int = 300

    # --- CI Mode ---
    ci_mode: bool = False  # True = use mock embedding + mock LLM

    # --- Execution ---
    execution_mode: str = "local"  # local | docker

    # --- API ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000


settings = Settings()
