"""The generated Power BI project: every reference resolves and the committed files match the spec.

Power BI treats a measure that names a missing column, or a visual bound to a missing
field, as an empty visual rather than an error, so these are checked here instead.
"""

import csv
import json
import re

import pytest

from decision_platform.bi import build_pbip
from decision_platform.bi.html_spec import CSS, HTML_MEASURES, HTML_VISUAL
from decision_platform.bi.model_spec import MEASURES, TABLES
from decision_platform.bi.report_spec import PAGES
from decision_platform.palette import OFFER_COLORS, OFFER_TEXTURE, SERIES
from decision_platform.simulation import OFFERS

COLUMN = re.compile(r"\b([a-z_]+)\[([a-z_]+)\]")
MEASURE = re.compile(r"(?<![\w\]])\[([^\[\]]+)\]")
STRING = re.compile(r'"(?:[^"]|"")*"')


def _columns() -> dict[str, set[str]]:
    out = {}
    for name in TABLES:
        with open(build_pbip.DATA_DIR / f"{name}.csv", encoding="utf-8") as handle:
            out[name] = set(next(csv.reader(handle)))
    return out


def _measure_names() -> set[str]:
    return {m[0] for m in MEASURES} | {m[0] for m in HTML_MEASURES}


@pytest.mark.parametrize("name,dax", [(m[0], m[1]) for m in MEASURES + HTML_MEASURES])
def test_every_measure_references_resolve(name, dax):
    columns, measures = _columns(), _measure_names()
    code = STRING.sub('""', dax)  # markup inside string literals is not a reference
    for table, column in COLUMN.findall(code):
        assert table in columns, f"{name}: unknown table {table}"
        assert column in columns[table], f"{name}: {table} has no column {column}"
    for reference in MEASURE.findall(code):
        assert reference in measures, f"{name}: unknown measure [{reference}]"


def test_every_visual_binds_to_something_that_exists():
    columns, measures = _columns(), _measure_names()
    keys = ("field", "measure", "x", "series", "rows", "columns_by", "color", "subtitle")
    for page in PAGES:
        for spec in page["visuals"]:
            if spec["type"] in {"page_header", "filters_button"}:
                continue  # Report UI measures, generated alongside the page
            refs = [spec[k] for k in keys if isinstance(spec.get(k), str)]
            refs += [r for k in ("y", "columns", "values") for r in spec.get(k, [])]
            for ref in refs:
                if ref.startswith("["):
                    assert ref.strip("[]") in measures, f"{page['name']}/{spec['id']}: {ref}"
                else:
                    table, column = ref.rstrip("]").split("[")
                    assert column in columns[table], f"{page['name']}/{spec['id']}: {ref}"


def test_html_panels_are_quote_safe():
    # The stylesheet is stored as a single-quoted PBIR literal, and HTML attributes
    # are single-quoted so DAX strings never need escaping.
    assert "'" not in CSS and '"' not in CSS
    for name, dax, *_ in HTML_MEASURES:
        for literal in STRING.findall(dax):
            assert '""' not in literal[1:-1], f"{name}: a double quote inside markup breaks the DAX string"


def test_html_visuals_are_registered_and_have_alt_text(tmp_path):
    stats = build_pbip.build(tmp_path)
    assert stats["pages"] == len(PAGES)
    report = json.loads((tmp_path / "Corridor.Report/definition/report.json").read_text(encoding="utf-8"))
    assert report["publicCustomVisuals"] == [HTML_VISUAL]
    html = [v for page in PAGES for v in page["visuals"] if v["type"] == "html"]
    assert len(html) >= 9 and all(len(v["alt"]) > 40 for v in html)
    command = next(p for p in PAGES if p["name"] == "p0_command")
    for spec in command["visuals"]:
        if spec["type"] == "html":
            assert 88 <= spec["pos"][1] and spec["pos"][1] + spec["pos"][3] <= 704


def test_committed_project_matches_the_spec():
    assert build_pbip.main(["--check"]) == 0


def test_offer_colours_come_from_the_validated_palette():
    assert set(OFFER_COLORS) == set(OFFERS)
    assert set(OFFER_COLORS.values()) <= set(SERIES)
    shared = {c for c in OFFER_COLORS.values() if list(OFFER_COLORS.values()).count(c) > 1}
    for colour in shared:
        owners = [o for o, c in OFFER_COLORS.items() if c == colour]
        # A shared slot is legal only with a second encoding on all but one owner.
        assert sum(o in OFFER_TEXTURE for o in owners) == len(owners) - 1
