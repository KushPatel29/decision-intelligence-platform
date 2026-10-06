"""Validate native report metadata against Microsoft's published JSON schemas."""
import json
import urllib.request
from pathlib import Path
import jsonschema
from referencing import Registry,Resource
from decision_platform.config import ROOT,write_json

def main():
    cache=ROOT/"outputs"/"powerbi_schema_cache";cache.mkdir(exist_ok=True)
    schemas={};count=0;errors=[]
    def retrieve(uri):
        if not uri.startswith("https://developer.microsoft.com/json-schemas/"):raise ValueError("Unexpected schema origin")
        if uri not in schemas:
            file=cache/(uri.replace("https://developer.microsoft.com/json-schemas/","").replace("/","_")+".json")
            if not file.exists():
                with urllib.request.urlopen(uri,timeout=40) as r:file.write_bytes(r.read())
            schemas[uri]=json.loads(file.read_text(encoding="utf-8-sig"))
        return schemas[uri]
    for path in (ROOT/"powerbi"/"Corridor").rglob("*"):
        if ".pbi" in path.parts:continue
        if path.suffix not in [".json",".pbip",".pbir"]:continue
        value=json.loads(path.read_text(encoding="utf-8"));uri=value.get("$schema")
        if not uri:continue
        try:
            schema=retrieve(uri)
            registry=Registry(retrieve=lambda address:Resource.from_contents(retrieve(address)))
            registry=registry.with_resource(uri,Resource.from_contents(schema))
            validator=jsonschema.validators.validator_for(schema)(schema,registry=registry)
            failures=list(validator.iter_errors(value))
            errors.extend({"file":str(path.relative_to(ROOT)),"path":list(e.absolute_path),"message":e.message} for e in failures)
            count+=1
        except Exception as exc:errors.append({"file":str(path.relative_to(ROOT)),"message":str(exc)})
    native=ROOT/"outputs/powerbi_desktop_validation.json"
    native_receipt=json.loads(native.read_text()) if native.exists() else {}
    receipt={"files_validated":count,"errors":errors,"schema_origin":"Microsoft published PBIP/PBIR JSON schemas","native_visual_rendering":"See separate Desktop refresh, DAX and visual review receipt" if native_receipt.get("status")=="passed" else "Pending Power BI Desktop; structural validation does not establish visual rendering"}
    write_json(ROOT/"outputs"/"powerbi_validation.json",receipt)
    print(json.dumps(receipt,indent=2))
    if errors:raise SystemExit(1)

if __name__=="__main__":main()
