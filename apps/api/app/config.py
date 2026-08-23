from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    database_path: Path

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            database_path=Path(
                os.getenv("EECP_DATABASE_PATH", "./data/eecp.db")
            ).resolve()
        )

