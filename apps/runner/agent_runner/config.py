from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    control_plane_url: str = "http://127.0.0.1:8080"
    runner_id: str = ""
    runner_token: str = ""
    runner_os: str = "macos"
    runner_poll_seconds: int = 3
    runner_artifact_dir: str = "./artifacts"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    task_timeout_seconds: int = 900
    browser_profile_dir: str = "~/.telegram-operator-agent/browser-profile"
    browser_headless: bool = False
    browser_timeout_seconds: int = 600


config = Config()
