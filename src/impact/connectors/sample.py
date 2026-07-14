"""Sample connector — loads synthetic metadata from ``fixtures/``.

Guarantees the demo runs end-to-end with zero credentials, and provides the
ground-truth dataset for the precision/recall validation.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..config import Settings
from .base import Connector, RawMetadata


class SampleConnector(Connector):
    def _load(self, *parts: str) -> RawMetadata:
        path = Path(self.settings.fixtures_path).joinpath(*parts)
        return json.loads(path.read_text())

    def get_databricks_metadata(self) -> RawMetadata:
        return self._load("databricks", "metadata.json")

    def get_tableau_metadata(self) -> RawMetadata:
        return self._load("tableau", "metadata.json")
