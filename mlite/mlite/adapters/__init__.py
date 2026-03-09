"""Adapter registry — dispatches to the correct FormatAdapter."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from mlite.adapters.base import FormatAdapter

_registry: Optional["AdapterRegistry"] = None


class AdapterRegistry:
    """Dispatches to the correct FormatAdapter based on file extension or MIME type."""

    def __init__(self) -> None:
        self._adapters: list[FormatAdapter] = []

    def register(self, adapter: FormatAdapter) -> None:
        self._adapters.append(adapter)

    def for_path(self, path: str | Path) -> Optional[FormatAdapter]:
        ext = Path(path).suffix.lstrip(".").lower()
        for adapter in self._adapters:
            if ext in adapter.source_extensions:
                return adapter
        return None

    def for_mime(self, mime: str) -> Optional[FormatAdapter]:
        for adapter in self._adapters:
            if adapter.source_mime == mime:
                return adapter
        return None


def get_registry() -> AdapterRegistry:
    """Return the lazily-initialised global registry."""
    global _registry
    if _registry is None:
        _registry = AdapterRegistry()
        _bootstrap(_registry)
    return _registry


def _bootstrap(registry: AdapterRegistry) -> None:
    from mlite.adapters.html import HTML_ADAPTER
    from mlite.adapters.markdown import MARKDOWN_ADAPTER
    from mlite.adapters.py_adapter import PYTHON_ADAPTER

    registry.register(MARKDOWN_ADAPTER)
    registry.register(HTML_ADAPTER)
    registry.register(PYTHON_ADAPTER)
