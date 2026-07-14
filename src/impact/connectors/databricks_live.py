"""Live Databricks connector.

Reads metadata from Unity Catalog ``information_schema`` and ``system`` tables
via an active Spark session (inside Databricks) or the Databricks SDK SQL
endpoint. Wired for the real environment; falls back with a clear error if no
execution context is available so callers can switch to sample mode.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..config import Settings
from .base import Connector, RawMetadata


class DatabricksLiveConnector(Connector):
    def __init__(self, settings: Settings):
        super().__init__(settings)
        self._spark = self._get_spark()

    @staticmethod
    def _get_spark():
        try:
            from pyspark.sql import SparkSession  # type: ignore

            return SparkSession.getActiveSession()
        except Exception:
            return None

    def _sql(self, query: str) -> List[Dict[str, Any]]:
        if self._spark is None:
            raise RuntimeError(
                "Live Databricks mode requires an active Spark session "
                "(run inside Databricks) — use mode: sample otherwise."
            )
        return [r.asDict() for r in self._spark.sql(query).collect()]

    def get_databricks_metadata(self) -> RawMetadata:
        catalog = self.settings.default_catalog
        schema = self.settings.default_schema
        ns = f"{catalog}.information_schema"

        cols = self._sql(
            f"""
            SELECT table_name, column_name, data_type
            FROM {ns}.columns
            WHERE table_catalog = '{catalog}' AND table_schema = '{schema}'
            ORDER BY table_name, ordinal_position
            """
        )
        tbls = self._sql(
            f"""
            SELECT table_name, table_type
            FROM {ns}.tables
            WHERE table_catalog = '{catalog}' AND table_schema = '{schema}'
            """
        )
        views = self._sql(
            f"""
            SELECT table_name AS name, view_definition AS sql
            FROM {ns}.views
            WHERE table_catalog = '{catalog}' AND table_schema = '{schema}'
            """
        )
        # Recent query history (e.g. Tableau extract refreshes / warehouse SQL).
        try:
            queries = self._sql(
                f"""
                SELECT statement_id AS id, statement_text AS sql, client_application AS source
                FROM system.query.history
                WHERE statement_text ILIKE '%{schema}.%'
                  AND start_time > current_timestamp() - INTERVAL 30 DAYS
                LIMIT 200
                """
            )
        except Exception:
            queries = []

        # Assemble table -> columns
        by_table: Dict[str, Dict[str, Any]] = {}
        type_by_table = {t["table_name"]: t.get("table_type", "TABLE") for t in tbls}
        for c in cols:
            t = c["table_name"]
            by_table.setdefault(t, {"name": t, "type": type_by_table.get(t, "TABLE"),
                                    "columns": []})
            by_table[t]["columns"].append(
                {"name": c["column_name"], "type": c.get("data_type", "")}
            )

        view_names = {v["name"] for v in views}
        tables = [v for k, v in by_table.items() if k not in view_names]

        return {
            "catalog": catalog,
            "schema": schema,
            "tables": tables,
            "views": [{"name": v["name"], "sql": v.get("sql") or ""} for v in views],
            "queries": queries,
            "column_lineage": self._column_lineage(catalog, schema),
        }

    def _column_lineage(self, catalog: str, schema: str) -> List[Dict[str, str]]:
        try:
            rows = self._sql(
                f"""
                SELECT
                  concat_ws('.', source_table_catalog, source_table_schema,
                            source_table_name, source_column_name) AS source,
                  concat_ws('.', target_table_catalog, target_table_schema,
                            target_table_name, target_column_name) AS target
                FROM system.access.column_lineage
                WHERE target_table_catalog = '{catalog}'
                  AND target_table_schema = '{schema}'
                  AND source_column_name IS NOT NULL
                """
            )
            return [{"source": r["source"], "target": r["target"]} for r in rows]
        except Exception:
            return []

    def get_tableau_metadata(self) -> RawMetadata:  # pragma: no cover - not used
        raise NotImplementedError("Use TableauLiveConnector for Tableau metadata.")
