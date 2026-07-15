from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _secret(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value.strip()

    file_path = os.getenv(f"{name}_FILE")
    if file_path:
        try:
            value = Path(file_path).read_text(encoding="utf-8").strip()
        except OSError as error:
            raise ValueError(f"failed to read {name}_FILE") from error
    if not value:
        raise ValueError(f"{name} is not configured")
    return value


BOT_TOKEN = _secret("BOT_TOKEN")
