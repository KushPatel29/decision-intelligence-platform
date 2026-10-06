"""Resume the official PyPI archive with checked ranges and SHA-256."""

import concurrent.futures
import hashlib
import json
import shutil
import urllib.request
from pathlib import Path

from decision_platform.config import ROOT


def main():
    metadata = json.load(urllib.request.urlopen("https://pypi.org/pypi/pyspark/4.0.1/json", timeout=30))[
        "urls"
    ][0]
    url, total = metadata["url"], metadata["size"]
    assert url.startswith("https://files.pythonhosted.org/")
    folder = ROOT / "outputs/downloads"
    folder.mkdir(exist_ok=True)
    target = folder / "pyspark-4.0.1.tar.gz"
    partial = Path(r"C:\Users\kush2\AppData\Local\Temp\pip-unpack-cgke54zx\pyspark-4.0.1.tar.gz")
    if not target.exists():
        shutil.copyfile(partial, target)
    start = target.stat().st_size
    chunk = 8 * 1024 * 1024
    segments = [(i, min(i + chunk, total) - 1) for i in range(start, total, chunk)]

    def retrieve(segment):
        begin, end = segment
        file = folder / f"part_{begin}_{end}"
        if file.exists() and file.stat().st_size == end - begin + 1:
            return file
        request = urllib.request.Request(url, headers={"Range": f"bytes={begin}-{end}"})
        with urllib.request.urlopen(request, timeout=60) as response:
            assert response.status == 206 and response.headers["Content-Range"].startswith(
                f"bytes {begin}-{end}/"
            )
            with file.open("wb") as output:
                shutil.copyfileobj(response, output, 256 * 1024)
        assert file.stat().st_size == end - begin + 1
        print(f"Downloaded range {begin:,}-{end:,}", flush=True)
        return file

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        parts = list(pool.map(retrieve, segments))
    with target.open("ab") as output:
        for part in parts:
            with part.open("rb") as source:
                shutil.copyfileobj(source, output)
    assert target.stat().st_size == total
    digest = hashlib.file_digest(target.open("rb"), "sha256").hexdigest()
    assert digest == metadata["digests"]["sha256"], "Archive checksum mismatch"
    print("Official PyPI archive checksum verified", flush=True)


if __name__ == "__main__":
    main()
