"""Implementation registry — reserved for future multi-backend support.

When a second backend (sqloxide, custom parser) is added, this module will
provide discovery and configuration for selecting the active implementation
at startup.  For now it is a placeholder that documents the extension point.
"""

from __future__ import annotations

# Currently unused — registered implementations go through
# ``_factory.register_implementation()``.
