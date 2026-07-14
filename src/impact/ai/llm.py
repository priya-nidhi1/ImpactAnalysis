"""Thin Mosaic AI client.

Calls a Databricks Foundation Model serving endpoint via the OpenAI-compatible
client exposed by the Databricks SDK. Returns ``None`` whenever no endpoint is
configured or reachable, so every caller can fall back to deterministic output
and the prototype runs fully offline.
"""

from __future__ import annotations

from typing import Optional

from ..config import Settings


def query_llm(
    prompt: str,
    settings: Settings,
    system: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: int = 700,
) -> Optional[str]:
    endpoint = settings.model_endpoint
    if not endpoint:
        return None
    try:
        from databricks.sdk import WorkspaceClient  # type: ignore

        client = WorkspaceClient().serving_endpoints.get_open_ai_client()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = client.chat.completions.create(
            model=endpoint,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content
    except Exception:
        # Any auth/network/SDK issue -> caller uses deterministic fallback.
        return None
