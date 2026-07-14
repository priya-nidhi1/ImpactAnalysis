"""Runtime configuration loaded from ``config/settings.yaml``.

Resolves the project root, the active mode (``sample`` | ``live``), target
catalogs/schemas, Tableau connection info, the Mosaic AI endpoint name and the
local data directory used by the JSON store fallback.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


def project_root() -> Path:
    # src/impact/config.py -> project root is two parents up from src/impact
    return Path(__file__).resolve().parents[2]


@dataclass
class Settings:
    mode: str = "sample"                       # "sample" | "live"
    catalogs: List[str] = field(default_factory=lambda: ["insurance"])
    schemas: List[str] = field(default_factory=lambda: ["policy"])
    default_catalog: str = "insurance"
    default_schema: str = "policy"
    sql_dialect: str = "databricks"

    # Tableau
    tableau_server: Optional[str] = None
    tableau_site: Optional[str] = None
    tableau_token_name: Optional[str] = None
    tableau_secret_scope: Optional[str] = None  # Databricks secret scope/key

    # Mosaic AI
    model_endpoint: Optional[str] = None        # e.g. "databricks-dbrx-instruct"

    # Storage
    metadata_schema: str = "impact_analysis"    # UC schema for Delta tables
    data_dir: str = ".data"                     # local JSON store dir
    fixtures_dir: str = "fixtures"

    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def data_path(self) -> Path:
        p = Path(self.data_dir)
        return p if p.is_absolute() else project_root() / p

    @property
    def fixtures_path(self) -> Path:
        p = Path(self.fixtures_dir)
        return p if p.is_absolute() else project_root() / p


def load_settings(path: Optional[str] = None) -> Settings:
    """Load settings from yaml, with env-var overrides for the active mode."""
    cfg_path = Path(path) if path else project_root() / "config" / "settings.yaml"
    data: Dict[str, Any] = {}
    if cfg_path.exists():
        data = yaml.safe_load(cfg_path.read_text()) or {}

    tableau = data.get("tableau", {}) or {}
    mosaic = data.get("mosaic_ai", {}) or {}
    storage = data.get("storage", {}) or {}

    settings = Settings(
        mode=os.environ.get("IMPACT_MODE", data.get("mode", "sample")),
        catalogs=data.get("catalogs", ["insurance"]),
        schemas=data.get("schemas", ["policy"]),
        default_catalog=data.get("default_catalog", "insurance"),
        default_schema=data.get("default_schema", "policy"),
        sql_dialect=data.get("sql_dialect", "databricks"),
        tableau_server=tableau.get("server"),
        tableau_site=tableau.get("site"),
        tableau_token_name=tableau.get("token_name"),
        tableau_secret_scope=tableau.get("secret_scope"),
        model_endpoint=mosaic.get("endpoint"),
        metadata_schema=storage.get("metadata_schema", "impact_analysis"),
        data_dir=storage.get("data_dir", ".data"),
        fixtures_dir=data.get("fixtures_dir", "fixtures"),
        raw=data,
    )
    return settings
