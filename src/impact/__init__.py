"""Change Impact Analysis — a Databricks-native prototype.

Predicts downstream impact of Databricks schema changes across Databricks
SQL/views and Tableau dashboards/data sources, before deployment.

The deterministic graph engine is the source of truth; the LLM layer only
phrases results and extracts intent from natural-language questions.
"""

__version__ = "0.1.0"
