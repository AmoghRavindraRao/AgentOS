"""DomainManager: maps a (user, slug) pair to a Cognee dataset_name.

Domain hot-swapping is a *consequence* of this mapping, not a feature: every
Cognee call is parameterized by dataset_name, so switching domains is one string
change with no pipeline rebuild.
"""

import re


class DomainManager:
    _SAFE_RE = re.compile(r"[^a-z0-9_]")

    def _safe(self, s: str) -> str:
        """Sanitize a user/slug string into a valid dataset identifier segment.

        Lowercase, non-alphanumerics collapsed to '_', capped at 32 chars.
        """
        return self._SAFE_RE.sub("_", s.lower())[:32]

    def dataset_name(self, user: str, slug: str) -> str:
        """Build the Cognee dataset name: ``u_{safe(user)}_d_{safe(slug)}``."""
        return f"u_{self._safe(user)}_d_{self._safe(slug)}"
