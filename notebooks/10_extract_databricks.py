# Databricks notebook source
# MAGIC %md
# MAGIC # 10 · Extract Databricks metadata
# MAGIC Pulls tables/columns/views from `information_schema`, parses view + query
# MAGIC SQL with sqlglot for column-level references, and persists the Databricks
# MAGIC slice of the dependency repository.

# COMMAND ----------

import sys, os
sys.path.insert(0, os.path.join(os.path.abspath(os.path.join(os.getcwd(), "..")), "src"))

from impact.config import load_settings
from impact.connectors import get_connector
from impact.extract import extract_databricks, extract_sql, schema_map_from_raw
from impact.store import get_store

settings = load_settings()
print("mode:", settings.mode)

# COMMAND ----------

db_raw = get_connector(settings).get_databricks_metadata()

nodes, edges = extract_databricks(db_raw)
n2, e2 = extract_sql(db_raw, dialect=settings.sql_dialect,
                     schema_map=schema_map_from_raw(db_raw))
nodes += n2
edges += e2

print(f"Databricks: {len(nodes)} nodes, {len(edges)} edges")

# COMMAND ----------

# Start the repository fresh with the Databricks slice (notebook 20 unions Tableau).
store = get_store(settings)
store.write_repository(nodes, edges)
print("persisted Databricks nodes/edges")

# COMMAND ----------

display(spark.createDataFrame(
    [(n.id, n.type.value, n.name) for n in nodes], ["id", "type", "name"]
))
