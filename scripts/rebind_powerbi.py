"""Update only this project's native BI import paths after relocating the release."""

import json
import re

from decision_platform.config import ROOT


def main():
    model = ROOT / "powerbi/Corridor/Corridor.SemanticModel/model.bim"
    value = json.loads(model.read_text(encoding="utf-8-sig"))
    for table in value["model"]["tables"]:
        for partition in table.get("partitions", []):
            source = partition.get("source", {})
            if source.get("type") != "m":
                continue
            expression = source["expression"]
            text = "\n".join(expression) if isinstance(expression, list) else expression

            def replace(match):
                filename = match.group(1).replace("\\", "/").split("/")[-1]
                target = ROOT / "outputs/powerbi" / filename
                if target.suffix != ".csv" or not target.is_file():
                    raise ValueError("Missing BI import: " + filename)
                return 'File.Contents("' + target.as_posix() + '")'

            text = re.sub(r'File\.Contents\("([^"]+)"\)', replace, text)
            source["expression"] = text.splitlines() if isinstance(expression, list) else text
    model.write_text(json.dumps(value, indent=2), encoding="utf-8")
    print("Power BI imports now point to this release folder")


if __name__ == "__main__":
    main()
