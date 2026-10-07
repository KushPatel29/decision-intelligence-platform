"""Run the four Databricks notebooks locally, in task order, before spending a hosted run on them.

Each notebook is executed as written, with real PySpark for reading and computing and a
stand-in ``dbutils`` (widgets, task values, notebook.exit). What a laptop cannot do is
replaced by a check rather than skipped:

* Table writes become temp views (local Spark on Windows cannot write tables without
  Hadoop's native binaries), and reads of ``catalog.schema.table`` resolve to them.
* ``ADD CONSTRAINT ... CHECK (rule)`` counts the rows that violate the rule and fails on
  any; ``PRIMARY KEY`` and ``SET NOT NULL`` test uniqueness and nulls. Delta enforces
  these on Databricks; here they are proven against the same data.
* ``OPTIMIZE``, ``COMMENT``, ``CREATE VOLUME`` and ``DESCRIBE HISTORY`` are recorded.
* MLflow tracking and the Unity Catalog registry go to a local SQLite store, so the
  registry task's log, register, alias and load-back round trip really runs.

Usage::

    python databricks/local_run.py [--customers 3000]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = ["pipeline", "lakehouse", "registry", "publish"]
CATALOG, SCHEMA = "spark_catalog", "corridor"


class NotebookExit(Exception):
    def __init__(self, value):
        super().__init__(value)
        self.value = value


class Widgets:
    def __init__(self, parameters):
        self.parameters, self.values = parameters, {}

    def text(self, name, default, label=None):
        self.values[name] = self.parameters.get(name, default)

    dropdown = None  # the notebooks use text widgets only

    def get(self, name):
        return self.values[name]


class TaskValues:
    def __init__(self):
        self.store, self.current = {}, None

    def set(self, key, value):
        self.store[(self.current, key)] = value

    def get(self, taskKey, key, default=None, debugValue=None):  # noqa: N803 (dbutils' own names)
        return self.store.get((taskKey, key), default)


class DBUtils:
    def __init__(self, parameters, task_values):
        self.widgets = Widgets(parameters)
        self.jobs = type("Jobs", (), {"taskValues": task_values})()
        self.library = type("Library", (), {"restartPython": staticmethod(lambda: None)})()
        self.notebook = type("Notebook", (), {"exit": staticmethod(self._exit)})()

    @staticmethod
    def _exit(value):
        raise NotebookExit(value)


class LocalSpark:
    """The real SparkSession, with table writes as temp views and Delta/UC DDL checked against data."""

    def __init__(self, spark):
        # Views are tracked here: asking Spark's catalog whether one exists initialises the Hadoop file
        # system layer, which is the thing this harness exists to avoid on Windows.
        self._spark, self.recorded, self.views = spark, [], set()

    def __getattr__(self, name):
        return getattr(self._spark, name)

    @staticmethod
    def view(name):
        return "v_" + re.sub(r"\W", "_", name)

    def _rewrite(self, query):
        return re.sub(rf"\b{CATALOG}\.{SCHEMA}\.(\w+)", lambda m: self.view(m.group(0)), query)

    def table(self, name):
        return self._spark.table(self.view(name))

    def createDataFrame(self, data, schema=None):  # noqa: N802 (Spark's name)
        """Local rows go through pandas and Arrow, which Spark converts without a Python worker process
        (local Python workers crash on this Windows setup; Databricks has no such problem)."""
        if isinstance(data, list) and isinstance(schema, str):
            import pandas as pd

            columns = [part.strip().split()[0] for part in schema.split(",")]
            data = pd.DataFrame(data, columns=columns)
        return self._spark.createDataFrame(data, schema)

    def _count(self, query):
        return self._spark.sql(self._rewrite(query)).first()[0]

    def sql(self, query):
        text = " ".join(query.split())
        upper = text.upper()
        if (
            upper.startswith(("CREATE SCHEMA", "CREATE VOLUME", "COMMENT ON", "OPTIMIZE"))
            or "DROP CONSTRAINT" in upper
        ):
            self.recorded.append(text)
            return None
        if upper.startswith("DESCRIBE HISTORY"):
            return self._spark.range(1)
        if upper.startswith("CREATE TABLE IF NOT EXISTS"):
            name, schema = re.match(
                r"CREATE TABLE IF NOT EXISTS (\S+) \((.*?)\)(?: COMMENT .*)?$", text
            ).groups()
            if self.view(name) not in self.views:
                # An empty frame built in the JVM: PySpark sends an empty pandas frame down its non-Arrow path.
                columns = [part.strip().split(None, 1) for part in schema.split(",")]
                empty = self._spark.range(0).selectExpr(
                    *[f"CAST(NULL AS {kind}) AS {col}" for col, kind in columns]
                )
                empty.createOrReplaceTempView(self.view(name))
                self.views.add(self.view(name))
            return None
        check = re.match(r"ALTER TABLE (\S+) ADD CONSTRAINT (\w+) CHECK \((.*)\)$", text)
        if check:
            table, constraint, rule = check.groups()
            bad = self._count(f"SELECT COUNT(*) FROM {table} WHERE NOT ({rule})")
            assert bad == 0, f"{constraint}: {bad} rows violate CHECK ({rule})"
            self.recorded.append(f"CHECK {constraint} held on every row")
            return None
        key = re.match(r"ALTER TABLE (\S+) ADD CONSTRAINT (\w+) PRIMARY KEY \((\w+)\)$", text)
        if key:
            table, constraint, column = key.groups()
            rows, distinct = self._spark.sql(
                self._rewrite(f"SELECT COUNT(*), COUNT(DISTINCT {column}) FROM {table}")
            ).first()
            assert rows == distinct, f"{constraint}: {column} is not unique"
            self.recorded.append(f"PRIMARY KEY {constraint} unique")
            return None
        not_null = re.match(r"ALTER TABLE (\S+) ALTER COLUMN (\w+) SET NOT NULL$", text)
        if not_null:
            table, column = not_null.groups()
            assert self._count(f"SELECT COUNT(*) FROM {table} WHERE {column} IS NULL") == 0
            return None
        return self._spark.sql(self._rewrite(query))


def patch_writes(local):
    from pyspark.sql import DataFrameWriter

    def save_as_table(writer, name, format=None, mode=None, partitionBy=None, **options):  # noqa: A002, N803
        frame, view = writer._df, local.view(name)
        # Delta refuses these characters in column names unless column mapping is on; a temp view would not.
        bad = [c for c in frame.columns if re.search(r"[ ,;{}()\n\t=]", c)]
        assert not bad, f"{name}: Delta rejects the column names {bad}"
        exists = view in local.views
        if (mode or getattr(writer, "_mode", None)) == "append" and exists:
            frame = local._spark.table(view).unionByName(frame)
        # Materialise: a view over a lazy plan would re-read files that later tasks replace.
        frame.localCheckpoint(eager=True).createOrReplaceTempView(view)
        local.views.add(view)

    original_mode = DataFrameWriter.mode

    def mode(writer, value):
        writer._mode = value
        return original_mode(writer, value)

    DataFrameWriter.saveAsTable = save_as_table
    DataFrameWriter.mode = mode


def patch_mlflow(store):
    import mlflow

    uri = "sqlite:///" + (store / "mlflow.db").as_posix()
    real_tracking, real_registry = mlflow.set_tracking_uri, mlflow.set_registry_uri
    mlflow.set_tracking_uri = lambda _uri: real_tracking(uri)
    mlflow.set_registry_uri = lambda _uri: real_registry(uri)
    real_experiment = mlflow.set_experiment
    mlflow.set_experiment = lambda name=None, **kw: real_experiment("corridor-local-harness")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--customers", default="3000")
    ap.add_argument(
        "--run-path",
        help="resume after the pipeline task, from the run folder it wrote (the volume path it printed)",
    )
    args = ap.parse_args()

    os.environ.setdefault("JAVA_HOME", r"C:\Program Files\Tableau\Tableau 2026.2\bin\jre")
    os.environ["PYSPARK_PYTHON"] = sys.executable
    os.environ["SPARK_LOCAL_IP"] = "127.0.0.1"
    scratch = Path(tempfile.mkdtemp(prefix="corridor-local-"))
    os.environ["CORRIDOR_VOLUME_ROOT"] = (scratch / "Volumes").as_posix()
    from pyspark.sql import SparkSession

    spark = (
        SparkSession.builder.master("local[2]")
        .appName("corridor-databricks-local")
        .config("spark.driver.memory", "3g")
        .config("spark.sql.shuffle.partitions", "8")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.execution.arrow.pyspark.enabled", "true")
        .config("spark.sql.execution.arrow.pyspark.fallback.enabled", "false")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")
    local = LocalSpark(spark)
    patch_writes(local)
    patch_mlflow(scratch)
    # The registry task would also send the pipeline's own runs to "databricks"; keep them local.
    os.environ["MLFLOW_TRACKING_URI"] = "sqlite:///" + (scratch / "mlflow.db").as_posix()

    parameters = {
        "code_root": ROOT.as_posix(),
        "catalog": CATALOG,
        "schema": SCHEMA,
        "customers": args.customers,
        "solver": "auto",
        "job_run_id": "local",
    }
    values, timings, exit_value = TaskValues(), {}, None
    try:
        if args.run_path:
            values.store[("pipeline", "run_path")] = Path(args.run_path).as_posix()
            values.store[("pipeline", "pipeline")] = json.dumps(
                {"run_id": Path(args.run_path).name, "resumed_from": "existing pipeline output"}
            )
        for index, task in enumerate(NOTEBOOKS, start=1):
            if args.run_path and task == "pipeline":
                continue
            path = next((ROOT / "databricks" / "notebooks").glob(f"{index:02d}_*.py"))
            values.current = task
            started = time.perf_counter()
            print(f"\n=== {task}: {path.name}", flush=True)
            namespace = {"spark": local, "dbutils": DBUtils(parameters, values), "__name__": "__main__"}
            if task == "pipeline":
                # The notebook points MLflow at the workspace; locally the run goes to SQLite.
                source = path.read_text(encoding="utf-8").replace(
                    'os.environ["MLFLOW_TRACKING_URI"] = "databricks"',
                    "pass  # local harness: SQLite tracking",
                )
            else:
                source = path.read_text(encoding="utf-8")
            try:
                exec(compile(source, str(path), "exec"), namespace)  # noqa: S102 - running our own notebooks
            except NotebookExit as done:
                exit_value = done.value
            timings[task] = round(time.perf_counter() - started, 1)
    finally:
        spark.stop()
    receipt = json.loads(exit_value) if exit_value else {}
    summary = {
        "status": receipt.get("status", "no receipt"),
        "task_seconds": timings,
        "delta_and_uc_statements_checked": local.recorded,
        "receipt": receipt,
    }
    out = ROOT / "tmp" / "databricks_local_run.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\nlocal run {summary['status']}; details in {out.relative_to(ROOT)}")
    shutil.rmtree(scratch, ignore_errors=True)
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
