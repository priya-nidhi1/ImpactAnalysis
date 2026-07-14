# Databricks notebook source
# MAGIC %md
# MAGIC # 40 · Impact demo — "What breaks if I rename policy_status?"
# MAGIC Runs the deterministic impact engine and the Mosaic AI summary for the
# MAGIC headline scenario, then reports precision/recall against the labeled
# MAGIC fixtures.

# COMMAND ----------

import sys, os
sys.path.insert(0, os.path.join(os.path.abspath(os.path.join(os.getcwd(), "..")), "src"))

from impact.config import load_settings
from impact.pipeline import load_graph, build_graph_in_memory
from impact.graph import analyze_change
from impact.ai.nl_change import parse_nl_change
from impact.ai.summarize import summarize_impact

settings = load_settings()
# load_graph() reads persisted tables; build_graph_in_memory() re-extracts live.
g = build_graph_in_memory(settings)

# COMMAND ----------

question = "What will be impacted if I rename policy_status?"
change = parse_nl_change(question, g, settings)
results = analyze_change(g, change)

display(spark.createDataFrame(
    [(r.severity.value, r.system.value, r.asset_type.value, r.asset_name, r.reason)
     for r in results],
    ["severity", "system", "asset_type", "asset", "why"],
))

# COMMAND ----------

# Mosaic AI summary (falls back to deterministic text if no endpoint configured).
print(summarize_impact(change, results, settings))

# COMMAND ----------

# MAGIC %md ## Accuracy vs labeled fixtures (precision / recall)

# COMMAND ----------

sys.path.insert(0, os.path.join(os.path.abspath(os.path.join(os.getcwd(), "..")), "scripts"))
from validate import precision_recall

for line in precision_recall(settings):
    print(line)
