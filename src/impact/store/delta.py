"""Persistence for the dependency repository.

Two interchangeable backends:

* ``LocalJsonStore`` — writes the four collections (nodes, edges,
  change_requests, impact_results) as JSON files under ``settings.data_dir``.
  Used for local/sample runs and unit tests; no Spark required.
* ``DeltaStore`` — writes Delta tables in Unity Catalog when a Spark session is
  available (i.e. running inside Databricks). This is the production path.

``get_store(settings)`` auto-selects based on Spark availability.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import Settings
from ..model import Edge, Node

_COLLECTIONS = ("nodes", "edges", "change_requests", "impact_results")


class MetadataStore(ABC):
    @abstractmethod
    def write_nodes(self, nodes: List[Node]) -> None: ...

    @abstractmethod
    def write_edges(self, edges: List[Edge]) -> None: ...

    @abstractmethod
    def read_nodes(self) -> List[Node]: ...

    @abstractmethod
    def read_edges(self) -> List[Edge]: ...

    @abstractmethod
    def write_records(self, collection: str, rows: List[Dict[str, Any]]) -> None: ...

    @abstractmethod
    def read_records(self, collection: str) -> List[Dict[str, Any]]: ...

    def write_repository(self, nodes: List[Node], edges: List[Edge]) -> None:
        self.write_nodes(nodes)
        self.write_edges(edges)


class LocalJsonStore(MetadataStore):
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, collection: str) -> Path:
        return self.data_dir / f"{collection}.json"

    def write_records(self, collection: str, rows: List[Dict[str, Any]]) -> None:
        assert collection in _COLLECTIONS, collection
        self._path(collection).write_text(json.dumps(rows, indent=2, default=str))

    def read_records(self, collection: str) -> List[Dict[str, Any]]:
        p = self._path(collection)
        if not p.exists():
            return []
        return json.loads(p.read_text())

    def write_nodes(self, nodes: List[Node]) -> None:
        self.write_records("nodes", [n.to_dict() for n in nodes])

    def write_edges(self, edges: List[Edge]) -> None:
        self.write_records("edges", [e.to_dict() for e in edges])

    def read_nodes(self) -> List[Node]:
        return [Node.from_dict(d) for d in self.read_records("nodes")]

    def read_edges(self) -> List[Edge]:
        return [Edge.from_dict(d) for d in self.read_records("edges")]


class DeltaStore(MetadataStore):
    """Delta-backed store for in-cluster runs. Tables live in
    ``{catalog}.{metadata_schema}.{collection}``."""

    def __init__(self, spark, target_schema: str):
        self.spark = spark
        self.schema = target_schema  # e.g. "main.impact_analysis"

    def _table(self, collection: str) -> str:
        return f"{self.schema}.{collection}"

    def write_records(self, collection: str, rows: List[Dict[str, Any]]) -> None:
        # Persist as JSON strings in a single column to stay schema-agnostic for
        # the prototype; downstream reads parse them back.
        payload = [(json.dumps(r, default=str),) for r in rows]
        df = self.spark.createDataFrame(payload, schema=["payload"])
        df.write.mode("overwrite").saveAsTable(self._table(collection))

    def read_records(self, collection: str) -> List[Dict[str, Any]]:
        rows = self.spark.table(self._table(collection)).collect()
        return [json.loads(r["payload"]) for r in rows]

    def write_nodes(self, nodes: List[Node]) -> None:
        self.write_records("nodes", [n.to_dict() for n in nodes])

    def write_edges(self, edges: List[Edge]) -> None:
        self.write_records("edges", [e.to_dict() for e in edges])

    def read_nodes(self) -> List[Node]:
        return [Node.from_dict(d) for d in self.read_records("nodes")]

    def read_edges(self) -> List[Edge]:
        return [Edge.from_dict(d) for d in self.read_records("edges")]


def _active_spark():
    try:
        from pyspark.sql import SparkSession  # type: ignore

        return SparkSession.getActiveSession()
    except Exception:
        return None


def get_store(settings: Settings, spark: Optional[Any] = None) -> MetadataStore:
    spark = spark or _active_spark()
    if spark is not None:
        catalog = settings.default_catalog
        return DeltaStore(spark, f"{catalog}.{settings.metadata_schema}")
    return LocalJsonStore(settings.data_path)
