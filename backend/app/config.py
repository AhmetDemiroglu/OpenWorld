from __future__ import annotations

from pathlib import Path
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[1]


def _resolve_from_backend(raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (_BACKEND_DIR / path).resolve()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: str = "http://localhost:5173"

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3.5:9b-q4_K_M"
    ollama_max_steps: int = 25
    ollama_request_timeout_sec: float = 600.0
    ollama_connect_timeout_sec: float = 20.0
    tesseract_cmd: str = ""

    workspace_root: str = "../data"
    sessions_dir: str = "../data/sessions"
    data_dir: str = "../data"

    enable_shell_tool: bool = True
    shell_allowed_prefixes: str = "*"
    shell_timeout_sec: int = 120
    allow_full_disk_access: bool = False
    fs_allowed_roots: str = ""

    web_allow_internet: bool = True
    web_allowed_domains: str = ""
    web_block_private_hosts: bool = True

    block_financial_operations: bool = True

    telegram_bot_token: str = ""
    telegram_bot_token_enc: str = ""
    telegram_allowed_user_id: str = ""
    gmail_access_token: str = ""
    gmail_access_token_enc: str = ""
    gmail_refresh_token: str = ""
    gmail_refresh_token_enc: str = ""
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_client_secret_enc: str = ""
    outlook_access_token: str = ""
    outlook_access_token_enc: str = ""
    outlook_refresh_token: str = ""
    outlook_refresh_token_enc: str = ""
    outlook_client_id: str = ""
    outlook_tenant_id: str = "common"
    owner_name: str = "Ahmet"
    owner_profile: str = "Teknoloji, otomasyon, urun gelistirme"
    assistant_name: str = "OpenWorld"

    # Background Services
    bg_email_monitor: bool = True
    bg_email_interval_min: int = 5
    bg_smart_assistant: bool = True
    bg_weather_city: str = "Izmir"
    bg_custom_alerts: str = ""

    # Agent / Telegram timeout tunables
    agent_timeout_default_sec: int = 240
    agent_timeout_research_sec: int = 420
    agent_timeout_resume_sec: int = 180
    agent_timeout_automation_sec: int = 180
    agent_timeout_media_sec: int = 25

    telegram_timeout_default_sec: int = 300
    telegram_timeout_research_sec: int = 420
    telegram_timeout_resume_sec: int = 420
    telegram_timeout_automation_sec: int = 240
    telegram_timeout_fast_sec: int = 45

    @property
    def cors_origins_list(self) -> List[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    @property
    def shell_allowed_prefixes_list(self) -> List[str]:
        if self.shell_allowed_prefixes == "*":
            return ["*"]
        return [x.strip() for x in self.shell_allowed_prefixes.split(",") if x.strip()]

    @property
    def web_allowed_domains_list(self) -> List[str]:
        return [x.strip().lower() for x in self.web_allowed_domains.split(",") if x.strip()]

    @property
    def fs_allowed_roots_list(self) -> List[Path]:
        roots: List[Path] = []
        for item in [x.strip() for x in self.fs_allowed_roots.split(",") if x.strip()]:
            try:
                roots.append(Path(item).expanduser().resolve())
            except Exception:
                continue
        return roots

    @property
    def workspace_path(self) -> Path:
        return _resolve_from_backend(self.workspace_root)

    @property
    def sessions_path(self) -> Path:
        return _resolve_from_backend(self.sessions_dir)

    @property
    def data_path(self) -> Path:
        return _resolve_from_backend(self.data_dir)

    @field_validator("port")
    @classmethod
    def validate_port(cls, value: int) -> int:
        if value < 1 or value > 65535:
            raise ValueError("PORT out of range")
        return value


settings = Settings()
