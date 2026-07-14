"""Live Tableau connector — Tableau Metadata API (GraphQL).

Uses a Personal Access Token (read from a Databricks secret scope) to query the
Metadata API for datasources, fields, calculated fields, worksheets and
dashboards plus their upstream database columns. The GraphQL query below maps
1:1 onto the raw metadata shape consumed by ``extract/tableau_meta.py``.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..config import Settings
from .base import Connector, RawMetadata

_GRAPHQL = """
{
  publishedDatasources {
    name
    fields {
      name
      upstreamColumns { name table { name fullName } }
    }
    ... on PublishedDatasource {
      calculatedFields: fields { name }
    }
  }
  workbooks {
    name
    dashboards { name sheets { name } }
    sheets {
      name
      ... on Worksheet {
        upstreamDatasources { name }
        sheetFieldInstances { name }
      }
    }
  }
}
"""


class TableauLiveConnector(Connector):
    def _token(self) -> str:
        scope = self.settings.tableau_secret_scope
        try:  # Databricks secret access
            from databricks.sdk.runtime import dbutils  # type: ignore

            return dbutils.secrets.get(scope=scope, key="tableau_pat")
        except Exception as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                f"Could not read Tableau PAT from secret scope {scope!r}: {exc}"
            )

    def _client(self):
        import tableauserverclient as tsc  # type: ignore

        auth = tsc.PersonalAccessTokenAuth(
            self.settings.tableau_token_name,
            self._token(),
            site_id=self.settings.tableau_site or "",
        )
        server = tsc.Server(self.settings.tableau_server, use_server_version=True)
        return server, auth

    def get_tableau_metadata(self) -> RawMetadata:
        server, auth = self._client()
        with server.auth.sign_in(auth):
            resp = server.metadata.query(_GRAPHQL)
        return _normalize(resp)

    def get_databricks_metadata(self) -> RawMetadata:  # pragma: no cover - not used
        raise NotImplementedError("Use DatabricksLiveConnector for Databricks metadata.")


def _normalize(resp: Dict[str, Any]) -> RawMetadata:
    """Reshape the Metadata API response into our raw fixture schema.

    The exact GraphQL response varies by Tableau version / Catalog enablement;
    this normalizer is intentionally defensive so a partial response still
    yields a usable (if smaller) graph.
    """
    data = resp.get("data", resp)
    datasources: List[Dict[str, Any]] = []
    for ds in data.get("publishedDatasources", []) or []:
        fields, calcs = [], []
        for f in ds.get("fields", []) or []:
            ups = f.get("upstreamColumns") or []
            if ups:
                fields.append(
                    {
                        "name": f["name"],
                        "upstreamColumns": [
                            {
                                "table": (c.get("table") or {}).get("fullName")
                                or (c.get("table") or {}).get("name"),
                                "name": c.get("name"),
                            }
                            for c in ups
                        ],
                    }
                )
            elif f.get("formula"):
                calcs.append({"name": f["name"], "formula": f.get("formula", "")})
        datasources.append(
            {"name": ds["name"], "fields": fields, "calculatedFields": calcs}
        )

    workbooks: List[Dict[str, Any]] = []
    for wb in data.get("workbooks", []) or []:
        worksheets = [
            {
                "name": s.get("name"),
                "datasource": ((s.get("upstreamDatasources") or [{}])[0]).get("name"),
                "fields": [fi.get("name") for fi in (s.get("sheetFieldInstances") or [])],
            }
            for s in wb.get("sheets", []) or []
        ]
        dashboards = [
            {"name": d.get("name"), "worksheets": [s.get("name") for s in d.get("sheets", [])]}
            for d in wb.get("dashboards", []) or []
        ]
        workbooks.append({"name": wb["name"], "worksheets": worksheets, "dashboards": dashboards})

    return {"datasources": datasources, "workbooks": workbooks}
