from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./agent.db"
    control_plane_bot_token: str
    approval_ttl_seconds: int = 900
    task_timeout_seconds: int = 900
    runner_offline_after_seconds: int = 20
settings = Settings()
