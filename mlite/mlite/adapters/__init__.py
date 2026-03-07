# mlite/adapters/__init__.py
# TODO: implement AdapterRegistry with for_path(), for_mime(), for_extension()
# See CLAUDE.md for dispatch requirements

from mlite.adapters.base import FormatAdapter

class AdapterRegistry:
    """Dispatches to the correct FormatAdapter based on file extension or MIME type."""
    pass
