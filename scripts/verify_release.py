"""Extract the portable archive and execute its own app in an isolated workspace."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from decision_platform.config import ROOT, write_json


def main():
    archive = ROOT / "release/Corridor-0.4.0.zip"
    parent = (ROOT / "tmp/release-verification").resolve()
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=parent) as directory:
        extracted = Path(directory).resolve()
        if not extracted.is_relative_to(parent):
            raise ValueError("Temporary workspace escaped its verification directory")
        with zipfile.ZipFile(archive) as bundle:
            for name in bundle.namelist():
                if not (extracted / name).resolve().is_relative_to(extracted):
                    raise ValueError("Unsafe archive member")
            bundle.extractall(extracted)
        environment = os.environ.copy()
        environment.update(
            CORRIDOR_ROOT=str(extracted),
            CORRIDOR_ENV="local",
            CORRIDOR_AUTH="local",
            PYTHONPATH=str(extracted / "src"),
        )
        code = """
import json,os
from pathlib import Path
from streamlit.testing.v1 import AppTest
from decision_platform.config import ROOT
from decision_platform.runtime import validate_release,saved_plans
assert ROOT==Path(os.environ["CORRIDOR_ROOT"])
release=validate_release(ROOT)
assert release["status"]=="verified"
pages=["Decision centre","Customer intelligence","Pricing","Promotions","Loyalty","Transportation","Experiments","Policy lab","Model operations","Operations centre","Analyst workbench","Evidence & delivery"]
app=AppTest.from_file(str(ROOT/"app.py"),default_timeout=30).run()
for page in pages:
    app.radio[0].set_value(page).run()
    assert not app.exception and not app.error,page
    assert app.title[0].value==page
app.radio[0].set_value("Decision centre").run()
app.selectbox[1].set_value("HiGHS").run()
app.number_input[0].set_value(400)
app.number_input[1].set_value(40)
app.button[0].click().run()
assert not app.exception and not app.error
scenario=app.session_state["scenario"]
assert scenario["diagnostics"]["all_constraints_passed"]
assert scenario["diagnostics"]["spend"]<=400+1e-6 and len(scenario["frame"])<=40
next(button for button in app.button if button.label=="Save reviewed scenario").click().run()
assert saved_plans(ROOT,"local-owner")[0]["release_id"]==release["release_id"]
app.radio[0].set_value("Pricing").run()
next(button for button in app.button if button.label=="Optimize price strategies").click().run()
assert not app.exception and not app.error
assert app.session_state["price_plan"][3]["all_constraints_passed"]
target=ROOT/"outputs/capacity.csv"
original=target.read_bytes()
target.write_bytes(original+b"corrupt")
try:
    validate_release(ROOT)
    raise AssertionError("Corruption was accepted")
except ValueError:pass
finally:target.write_bytes(original)
print(json.dumps({"status":"passed","release_id":release["release_id"],"workspaces":len(pages),"highs_campaign":True,"joint_price_campaign":True,"persisted_plan":True,"corruption_rejected":True}))
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=extracted,
            env=environment,
            capture_output=True,
            text=True,
            timeout=180,
        )
        (ROOT / "outputs/release_smoke.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            raise RuntimeError("Extracted release failed; inspect outputs/release_smoke.log")
        receipt = json.loads(result.stdout.strip().splitlines()[-1])
        receipt["archive_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
        receipt["scope"] = (
            "Extracted precomputed app; installed local runtime reused. No hosted or clean container execution claimed."
        )
        write_json(ROOT / "release/package_smoke.json", receipt)
        print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
