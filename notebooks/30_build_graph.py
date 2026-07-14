# Databricks notebook source
# MAGIC %md
# MAGIC # 30 · Build the dependency graph
# MAGIC Loads the persisted nodes/edges into a single cross-system graph and shows
# MAGIC where the Databricks and Tableau subgraphs join (the `maps_to` bridges).

# COMMAND ----------

import sys, os
sys.path.insert(0, os.path.join(os.path.abspath(os.path.join(os.getcwd(), "..")), "src"))

from collections import Counter
from impact.config import load_settings
from impact.pipeline import load_graph

settings = load_settings()
g = load_graph(settings)
print(f"Graph: {g.number_of_nodes()} nodes, {g.number_of_edges()} edges")

# COMMAND ----------

node_types = Counter(d["node"].type.value for _, d in g.nodes(data=True))
edge_types = Counter(d["etype"] for *_, d in g.edges(data=True))
print("nodes by type:", dict(node_types))
print("edges by type:", dict(edge_types))

# COMMAND ----------

# Cross-system bridges: Databricks column -> Tableau field
bridges = [(u, v) for u, v, d in g.edges(data=True) if d["etype"] == "maps_to"]
for u, v in bridges:
    print(f"{g.nodes[u]['node'].name}  ->  {g.nodes[v]['node'].name}")
