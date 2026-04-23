from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class PyfuseError(Exception):
    """Base error for pyfuse."""


@dataclass
class UnsupportedFeatureError(PyfuseError):
    message: str
    file: Path | None = None
    lineno: int | None = None

    def __str__(self) -> str:
        parts = [self.message]
        if self.file is not None:
            loc = str(self.file)
            if self.lineno is not None:
                loc = f"{loc}:{self.lineno}"
            parts.append(f"location={loc}")
        return " | ".join(parts)


@dataclass
class ResolutionError(PyfuseError):
    message: str
    file: Path | None = None
    lineno: int | None = None

    def __str__(self) -> str:
        parts = [self.message]
        if self.file is not None:
            loc = str(self.file)
            if self.lineno is not None:
                loc = f"{loc}:{self.lineno}"
            parts.append(f"location={loc}")
        return " | ".join(parts)
