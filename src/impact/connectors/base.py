"""Connector abstraction.

A connector produces *raw* metadata dicts that mimic the shape of the live
source APIs. The ``extract`` modules turn that raw metadata into graph nodes and
edges. This indirection lets the sample connector (fixtures) and the live
connectors (Databricks / Tableau) be fully interchangeable.

Raw metadata shape
------------------
``get_databricks_metadata()`` -> {
    "catalog": str, "schema": str,
    "tables":  [{"name", "type", "tags"?, "definition"?,
                 "columns": [{"name", "type", "tags"?}]}],
    "views":   [{"name", "sql"}],
    "queries": [{"id", "sql", "source"}],
    "column_lineage": [{"source", "target"}]   # optional fq column->column
}

``get_tableau_metadata()`` -> {
    "datasources": [{"name", "fields": [{"name", "upstreamColumns":[{"table","name"}]}],
                     "calculatedFields": [{"name", "formula"}]}],
    "workbooks":   [{"name", "worksheets": [{"name","datasource","fields":[...]}],
                     "dashboards": [{"name","worksheets":[...], "tags"?}]}]
}

``tags`` are optional ``{key: value}`` governance tags (Unity Catalog table /
column tags, Tableau tags): ``cde``, ``data_tier``, ``criticality``,
``data_owner``. See :mod:`impact.governance.load`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict

from ..config import Settings

RawMetadata = Dict[str, Any]


class Connector(ABC):
    def __init__(self, settings: Settings):
        self.settings = settings

    @abstractmethod
    def get_databricks_metadata(self) -> RawMetadata: ...

    @abstractmethod
    def get_tableau_metadata(self) -> RawMetadata: ...


def get_connector(settings: Settings) -> Connector:
    """Factory: pick the connector implementation for the active mode."""
    if settings.mode == "live":
        from .databricks_live import DatabricksLiveConnector
        from .tableau_live import TableauLiveConnector

        return _CompositeLiveConnector(settings)
    from .sample import SampleConnector

    return SampleConnector(settings)


class _CompositeLiveConnector(Connector):
    """Bridges the two live connectors behind the single Connector interface."""

    def __init__(self, settings: Settings):
        super().__init__(settings)
        from .databricks_live import DatabricksLiveConnector
        from .tableau_live import TableauLiveConnector

        self._databricks = DatabricksLiveConnector(settings)
        self._tableau = TableauLiveConnector(settings)

    def get_databricks_metadata(self) -> RawMetadata:
        return self._databricks.get_databricks_metadata()

    def get_tableau_metadata(self) -> RawMetadata:
        return self._tableau.get_tableau_metadata()
