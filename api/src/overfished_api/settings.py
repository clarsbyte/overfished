from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    agent_backend: str = "noop"
    fetch_agent_timeout_seconds: float = 2.5
    fetch_agent_max_retries: int = 1
    fetch_agent_enabled: bool = True
