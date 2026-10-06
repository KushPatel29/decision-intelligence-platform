"""Render the report's HTML panels at their positions on each page, outside Power BI.

The HTML Content visual renders a measure's markup with the stylesheet in
``decision_platform.bi.html_spec``. This page does the same with the markup the
engine actually returned (written by ``scripts/validate_powerbi_model.ps1``), at
each visual's position and size after the report chrome's reflow, and flags any
panel whose content overflows its box. Native visuals are drawn as labelled outlines.

Usage::

    python scripts/preview_powerbi_html.py [--measures tmp/powerbi_html_measures.json] [--out tmp/powerbi_html_preview.html]
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

from decision_platform.bi.html_spec import CSS
from decision_platform.bi.report_spec import PAGES

ROOT = Path(__file__).resolve().parents[1]

FRAME = "padding:10px;background:#0d2030;border:1px solid #263f52;border-radius:12px;"
PAGE_CSS = """
body{background:#050d16;color:#eef8ff;font-family:Segoe UI,sans-serif;margin:16px}
h2{font-size:14px;color:#8faebf;margin:18px 0 8px}
.canvas{position:relative;width:1280px;height:720px;background:#081522;outline:1px solid #263f52}
.vis{position:absolute;box-sizing:border-box;overflow:auto}
.vis.overflow{outline:2px solid #e66767}
.stub{position:absolute;box-sizing:border-box;border:1px dashed #2d4c61;border-radius:10px;color:#5b7486;font-size:11px;padding:6px}
"""
# Marks any panel whose markup does not fit, so a reviewer sees it without measuring.
CHECK = """
<script>
for (const v of document.querySelectorAll('.vis')) {
  if (v.scrollHeight > v.clientHeight + 1 || v.scrollWidth > v.clientWidth + 1) v.classList.add('overflow');
}
</script>
"""


def render(values: dict[str, str], pages: set[str] | None = None) -> str:
    sections = []
    for page in PAGES:
        if pages and page["name"] not in pages:
            continue
        items = []
        for spec in page["visuals"]:
            if spec.get("group") or spec["type"] == "filter_panel":
                continue  # the filter panel is hidden until its button is pressed
            x, y, w, h = spec["pos"]
            box = f"left:{x}px;top:{y}px;width:{w}px;height:{h}px;"
            if spec["type"] == "html":
                name = spec["measure"].strip("[]")
                style = box + (FRAME if spec.get("framed", True) else "")
                items.append(
                    f'<div class="vis" data-measure="{html.escape(name)}" style="{style}">{values[name]}</div>'
                )
            else:
                label = spec.get("title") or spec.get("label") or spec["type"]
                items.append(f'<div class="stub" style="{box}">{html.escape(str(label))}</div>')
        sections.append(f'<h2>{html.escape(page["display"])}</h2><div class="canvas">{"".join(items)}</div>')
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Corridor HTML panels</title>'
        f"<style>{PAGE_CSS}</style><style>{CSS}</style></head><body>{''.join(sections)}{CHECK}</body></html>"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--measures", type=Path, default=ROOT / "tmp" / "powerbi_html_measures.json")
    ap.add_argument("--out", type=Path, default=ROOT / "tmp" / "powerbi_html_preview.html")
    ap.add_argument("--pages", help="comma-separated page names, e.g. p0_command (default: all)")
    ap.add_argument(
        "--bare", action="store_true", help="no page titles or margins: one canvas, for a screenshot"
    )
    args = ap.parse_args()
    values = json.loads(args.measures.read_text(encoding="utf-8-sig"))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    page = render(values, set(args.pages.split(",")) if args.pages else None)
    if args.bare:
        page = page.replace("margin:16px}", "margin:0}").replace("<h2>", '<h2 style="display:none">')
        page = page.replace(".stub{position", ".stub{display:none;position")
        # The report draws its page header and navigation in the top 88px; the image starts below them.
        page = page.replace(".canvas{position:relative;", ".canvas{position:relative;margin-top:-80px;")
    args.out.write_text(page, encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
