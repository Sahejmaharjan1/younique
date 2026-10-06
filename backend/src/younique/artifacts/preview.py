from __future__ import annotations

import csv
import io
import json
import re

from younique.artifacts.scan import png_pixels


def sanitize_svg(text: str) -> str:
    without_scripts = re.sub(
        r"<script\b[^>]*>.*?</script>", "", text, flags=re.IGNORECASE | re.DOTALL
    )
    without_handlers = re.sub(
        r"\son\w+\s*=\s*(['\"]).*?\1", "", without_scripts, flags=re.IGNORECASE | re.DOTALL
    )
    return without_handlers


def _truncate(value: object, depth: int = 0) -> object:
    if depth > 6:
        return "…"
    if isinstance(value, dict):
        items = list(value.items())[:40]
        return {str(key): _truncate(item, depth + 1) for key, item in items}
    if isinstance(value, list):
        return [_truncate(item, depth + 1) for item in value[:40]]
    if isinstance(value, str) and len(value) > 500:
        return value[:500]
    return value


def build_preview(data: bytes, mime: str, name: str) -> dict[str, object]:
    if mime == "application/json":
        try:
            parsed: object = json.loads(data)
        except json.JSONDecodeError:
            parsed = None
        return {"kind": "json", "value": _truncate(parsed)}
    if mime in {"text/csv", "text/tab-separated-values"} or name.lower().endswith(".csv"):
        text = data.decode("utf-8", errors="replace")
        rows = list(csv.reader(io.StringIO(text)))
        width = max((len(row) for row in rows), default=0)
        head = rows[:100]
        return {
            "kind": "csv",
            "columns": head[0] if head else [],
            "rows": head[1:] if len(head) > 1 else [],
            "row_count": max(len(rows) - 1, 0),
            "column_count": width,
        }
    if mime == "application/pdf" or data.startswith(b"%PDF"):
        pages = data.count(b"/Type /Page")
        return {
            "kind": "pdf",
            "page_count": pages or 1,
            "excerpt": data[:200].decode("latin-1", errors="replace"),
        }
    if mime == "image/png":
        pixels = png_pixels(data)
        width = int.from_bytes(data[16:20], "big") if len(data) >= 24 else 0
        height = int.from_bytes(data[20:24], "big") if len(data) >= 24 else 0
        return {"kind": "image", "width": width, "height": height, "pixels": pixels or 0}
    if mime == "image/svg+xml":
        return {
            "kind": "svg",
            "sanitized": sanitize_svg(data.decode("utf-8", errors="replace"))[:8000],
        }
    excerpt = data.decode("utf-8", errors="replace")[:4000]
    return {"kind": "text", "excerpt": excerpt}
