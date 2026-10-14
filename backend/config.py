from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    modbus_host: str | None = Field(default=None, alias="MODBUS_HOST")
    modbus_port: int = Field(default=502, alias="MODBUS_PORT", ge=1, le=65535)
    modbus_unit_id: int = Field(default=255, alias="MODBUS_UNIT_ID", ge=0, le=255)
    register_profile: str = Field(default="core", alias="REGISTER_PROFILE", min_length=1)
    collector_enabled: bool = Field(default=False, alias="COLLECTOR_ENABLED")
    data_dir: Path = Field(default=Path("/data"), alias="DATA_DIR")
    display_timezone: str = Field(default="Europe/Vienna", alias="DISPLAY_TIMEZONE")

    @field_validator("modbus_host", mode="before")
    @classmethod
    def normalize_host(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("display_timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("DISPLAY_TIMEZONE must name an installed IANA time zone") from exc
        return value

    @model_validator(mode="after")
    def require_host_for_enabled_collector(self) -> "Settings":
        if self.collector_enabled and self.modbus_host is None:
            raise ValueError("MODBUS_HOST is required when COLLECTOR_ENABLED=true")
        return self

    def public_summary(self) -> dict[str, str | int | bool]:
        """Expose operational flags without returning private endpoint or path values."""
        return {
            "host_configured": self.modbus_host is not None,
            "modbus_port": self.modbus_port,
            "modbus_unit_id": self.modbus_unit_id,
            "register_profile": self.register_profile,
            "collector_enabled": self.collector_enabled,
            "display_timezone": self.display_timezone,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
