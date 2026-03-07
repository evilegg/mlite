# mlite/adapters/base.py
from dataclasses import dataclass
from typing import Callable

@dataclass
class FormatAdapter:
    source_mime: str
    source_extensions: list[str]
    to_mlite: Callable[..., str]
    from_mlite: Callable[..., str] | None  # None if conversion is lossy
