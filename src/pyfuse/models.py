from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ImportRequest:
    module: str | None
    names: tuple[str, ...]
    level: int
    lineno: int


@dataclass
class ModuleInfo:
    name: str
    path: Path
    is_package: bool
    source: str
    imports: list[ImportRequest] = field(default_factory=list)
    dependencies: set[str] = field(default_factory=set)
