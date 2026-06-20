"""
ACELink configuration helpers.

Settings are stored in a JSON file next to the app so the web UI can
read and update them directly.
"""

import json
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, field_validator

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "acelink.config.json"

DEVICE_MODELS = {"auto", "ace_pro", "ace_2_pro"}


class SlotTuning(BaseModel):
    custom: bool = False
    feed_length: int | None = Field(default=None, ge=0)
    load_length: int | None = Field(default=None, ge=0)
    retract_length: int | None = Field(default=None, ge=0)
    feed_speed: int | None = Field(default=None, ge=1)
    retract_speed: int | None = Field(default=None, ge=1)


def default_slot_tuning() -> list[SlotTuning]:
    return [SlotTuning() for _ in range(4)]


class AcelinkSettings(BaseModel):
    port: int = Field(default=8765, ge=1, le=65535)
    device_model: str = "auto"
    serial_port: str = ""
    baudrate: int = Field(default=230400, ge=1)
    protocol_debug: bool = False
    load_length: int = Field(default=2100, ge=0)
    retract_length: int = Field(default=1950, ge=0)
    feed_speed: int = Field(default=80, ge=1)
    retract_speed: int = Field(default=30, ge=1)
    scan_interval: int = Field(default=15, ge=1)
    feed_check_len: int = Field(default=254, ge=1, le=255)
    feed_check_error_len: int = Field(default=254, ge=1, le=255)
    slot_tuning: list[SlotTuning] = Field(default_factory=default_slot_tuning, min_length=4, max_length=4)

    @field_validator("device_model")
    @classmethod
    def normalize_device_model(cls, value: str) -> str:
        return value if value in DEVICE_MODELS else "auto"


class AcelinkSettingsPatch(BaseModel):
    port: int | None = Field(default=None, ge=1, le=65535)
    device_model: str | None = None
    serial_port: str | None = None
    baudrate: int | None = Field(default=None, ge=1)
    protocol_debug: bool | None = None
    load_length: int | None = Field(default=None, ge=0)
    retract_length: int | None = Field(default=None, ge=0)
    feed_speed: int | None = Field(default=None, ge=1)
    retract_speed: int | None = Field(default=None, ge=1)
    scan_interval: int | None = Field(default=None, ge=1)
    feed_check_len: int | None = Field(default=None, ge=1, le=255)
    feed_check_error_len: int | None = Field(default=None, ge=1, le=255)
    slot_tuning: list[SlotTuning] | None = Field(default=None, min_length=4, max_length=4)


def load_settings() -> AcelinkSettings:
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON in {CONFIG_PATH}: {exc}") from exc
    else:
        data = {}

    try:
        settings = AcelinkSettings.model_validate(data)
    except ValidationError as exc:
        raise RuntimeError(f"Invalid settings in {CONFIG_PATH}: {exc}") from exc

    save_settings(settings)
    return settings


def save_settings(settings: AcelinkSettings) -> None:
    CONFIG_PATH.write_text(
        json.dumps(settings.model_dump(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
