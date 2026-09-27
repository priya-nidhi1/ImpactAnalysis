"""PDF impact report: the HTML report template rendered by an HTML-to-PDF engine.

Engines, in order of preference:

* **WeasyPrint** — best CSS fidelity (paged media, page counters, footers).
  Needs the Pango system library; if it is missing, importing WeasyPrint
  raises ``OSError`` and we fall back.
* **xhtml2pdf** — pure Python, installs anywhere pip does. The report template
  (:func:`impact.report.report_html`) sticks to table layout and literal
  colours so it renders correctly here too.

Set ``IMPACT_PDF_ENGINE=weasyprint|xhtml2pdf`` to force one engine.
"""

from __future__ import annotations

import io
import logging
import os
from functools import lru_cache
from typing import List, Optional

from .model import ChangeRequest, ImpactAssessment, ImpactResult
from .report import report_html

log = logging.getLogger(__name__)

ENGINES = ("weasyprint", "xhtml2pdf")


def _weasyprint_ok() -> bool:
    try:
        import weasyprint  # noqa: F401  (loads Pango via cffi at import time)
    except (ImportError, OSError) as exc:
        log.info("WeasyPrint unavailable (%s); using xhtml2pdf", exc)
        return False
    return True


def _xhtml2pdf_ok() -> bool:
    try:
        import xhtml2pdf  # noqa: F401
    except ImportError:
        return False
    return True


@lru_cache(maxsize=None)
def pdf_engine() -> Optional[str]:
    """The engine that will render PDFs here, or None if neither is installed."""
    forced = os.environ.get("IMPACT_PDF_ENGINE", "").strip().lower()
    if forced:
        if forced not in ENGINES:
            raise ValueError(f"IMPACT_PDF_ENGINE must be one of {ENGINES}, got {forced!r}")
        return forced
    if _weasyprint_ok():
        return "weasyprint"
    if _xhtml2pdf_ok():
        return "xhtml2pdf"
    return None


def html_to_pdf(html: str, engine: Optional[str] = None) -> bytes:
    engine = engine or pdf_engine()
    if engine == "weasyprint":
        from weasyprint import HTML

        return HTML(string=html).write_pdf()
    if engine == "xhtml2pdf":
        from xhtml2pdf import pisa

        out = io.BytesIO()
        status = pisa.CreatePDF(html, dest=out, encoding="utf-8")
        if status.err:
            raise RuntimeError(f"xhtml2pdf failed to render the report ({status.err} errors)")
        return out.getvalue()
    raise RuntimeError("No PDF engine installed: pip install weasyprint (or xhtml2pdf)")


def report_pdf(change: ChangeRequest, results: List[ImpactResult],
               assessment: ImpactAssessment, engine: Optional[str] = None) -> bytes:
    return html_to_pdf(report_html(change, results, assessment), engine)
