# Databricks notebook source
# MAGIC %md
# MAGIC # 00 · Setup — catalog, schema, volume, package
# MAGIC Creates the Unity Catalog objects that hold the dependency repository and
# MAGIC makes the `impact` package importable. Idempotent — safe to re-run.

# COMMAND ----------

# MAGIC %pip install sqlglot networkx pyyaml tableauserverclient databricks-sdk
# MAGIC %restart_python

# COMMAND ----------

CATALOG = "insurance"            # default_catalog in config/settings.yaml
META_SCHEMA = "impact_analysis"  # storage.metadata_schema

spark.sql(f"CREATE CATALOG IF NOT EXISTS {CATALOG}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{META_SCHEMA}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{META_SCHEMA}.fixtures")
print(f"Ready: {CATALOG}.{META_SCHEMA} (+ fixtures volume)")

# COMMAND ----------

# Make the repo's src/ importable (this notebook lives in notebooks/).
import sys, os
REPO_ROOT = os.path.abspath(os.path.join(os.getcwd(), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

import impact
print("impact version:", impact.__version__)

# COMMAND ----------

# MAGIC %md
# MAGIC **Secrets (live mode).** Store the Tableau PAT once:
# MAGIC ```
# MAGIC databricks secrets create-scope impact_analysis
# MAGIC databricks secrets put-secret impact_analysis tableau_pat
# MAGIC ```
# MAGIC Then set `mode: live` in `config/settings.yaml` (or `IMPACT_MODE=live`).
