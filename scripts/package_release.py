"""Bundle runnable app results, native BI, executive brief and source evidence."""
import hashlib,json,zipfile,subprocess
from decision_platform.config import ROOT,write_json

def main():
    folder=ROOT/"release";folder.mkdir(exist_ok=True)
    files=[]
    for name in ["src","sql","app.py","web","tests","docs","adhoc","aws","databricks","scripts","powerbi",".streamlit",".github","output/pdf","README.md","START_HERE.md","PROJECT_STATUS.md","ROADMAP.md","DECISIONS.md","CHANGELOG.md","pyproject.toml","requirements-local.lock","requirements-runtime.txt","Dockerfile","compose.yaml",".dockerignore",".gitignore",".gitattributes"]:
        path=ROOT/name
        if path.is_file():files.append(path)
        elif path.exists():files.extend(p for p in path.rglob("*") if p.is_file())
    out=ROOT/"outputs"
    files.extend(p for p in out.iterdir() if p.suffix in [".json",".csv",".html",".png",".jpg"] and p.name != "repro_reference.json")
    files.extend((out/"powerbi").glob("*.csv"))
    files.extend((out/"performance").glob("*.csv"))
    files.extend((out/"models").glob("*.json"))
    files.extend((out/"adhoc").glob("*.csv"))
    files.extend((out/"adhoc").glob("*.md"))
    files.extend((out/"cloud_portfolio/definitions").glob("*.json"))
    files.append(out/"test_run.log")
    excluded={"replace_allocation.py","download_spark.py","check_clv.py"}
    files=sorted(set(p for p in files if p.name not in excluded|{"secrets.toml"} and "__pycache__" not in p.parts and ".pbi" not in p.parts and p.suffix not in [".pyc",".abf"]))
    archive=folder/"Corridor-0.4.0.zip"
    with zipfile.ZipFile(archive,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in files:z.write(path,path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        names=z.namelist()
        assert all(not n.startswith(("data/",".venv/","mlruns/")) for n in names)
        assert "app.py" in names and "outputs/dashboard_data.json" in names
        assert "output/pdf/executive_brief.pdf" in names
        assert "powerbi/Corridor/Corridor.pbip" in names
        manifest=json.loads(z.read("outputs/artifact_manifest.json"))
        for name,digest in manifest["files"].items():
            assert hashlib.sha256(z.read("outputs/"+name)).hexdigest()==digest, name
    source_sha=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    pipeline=json.loads((out/"manifest.json").read_text())
    receipt={"status":"passed","release":"0.4.0","source_git_sha":source_sha,"pipeline_git_sha":pipeline["git_sha"],"file_count":len(files),"archive":archive.name,"bytes":archive.stat().st_size,"sha256":hashlib.sha256(archive.read_bytes()).hexdigest(),"zip_integrity_passed":True,"excludes":["credentials","local audit records","virtual environment","simulator oracle","raw datasets","model binaries","native BI local cache","download archives"]}
    write_json(folder/"release_manifest.json",receipt);print(json.dumps(receipt,indent=2))

if __name__=="__main__":main()
