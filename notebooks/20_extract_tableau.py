# Databricks notebook source
# MAGIC %md
# MAGIC # 20 · Extract Tableau metadata + bridge
# MAGIC Pulls datasources/fields/calculated-fields/worksheets/dashboards from the
# MAGIC Tableau Metadata API and bridges Tableau fields to Databricks columns via
# MAGIC `maps_to` edges. Unions the result into the repository from notebook 10.

# COMMAND ----------

import sys, os
sys.path.insert(0, os.path.join(os.path.abspath(os.path.join(os.getcwd(), "..")), "src"))

from impact.config import load_settings
from impact.connectors import get_connector
from impact.extract import extract_tableau
from impact.pipeline import merge_into_store
from impact.store import get_store

settings = load_settings()

# COMMAND ----------

tab_raw = get_connector(settings).get_tableau_metadata()
nodes, edges = extract_tableau(
    tab_raw,
    default_catalog=settings.default_catalog,
    default_schema=settings.default_schema,
)
print(f"Tableau: {len(nodes)} nodes, {len(edges)} edges "
      f"({sum(1 for e in edges if e.type.value == 'maps_to')} cross-system bridges)")

# COMMAND ----------

store = get_store(settings)
merge_into_store(store, nodes, edges)
print(f"repository now has {len(store.read_nodes())} nodes, {len(store.read_edges())} edges")
