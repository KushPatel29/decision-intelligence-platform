"""The README's test badge is a claim about this suite, and the portfolio card repeats it.

Hold the badge to what pytest actually collects, so adding or removing a test without updating the badge fails
here rather than leaving a stale number on the README and every page that quotes it.
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_readme_badge_matches_the_collected_suite():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    badge = re.search(r"badge/tests-(\d+)%20(?:passing|collected)", readme)
    assert badge, "README.md has no tests-N badge"
    collected = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    count = re.search(r"(\d+) tests? collected", collected)
    assert count, collected[-2000:]
    assert int(badge.group(1)) == int(count.group(1))
