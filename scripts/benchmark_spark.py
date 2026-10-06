"""Execute million-row local Spark features and real Delta Lake writes/readback."""

import os
import time

import numpy as np
import pandas as pd

from decision_platform.config import ROOT, write_json
from decision_platform.features import FEATURES


def main():
    import pyarrow.parquet as pq
    from deltalake import DeltaTable, write_deltalake
    from pyspark.sql import SparkSession

    from decision_platform.spark_features import build_features

    os.environ.setdefault("JAVA_HOME", r"C:\Program Files\Tableau\Tableau 2026.2\bin\jre")
    os.environ["PYSPARK_PYTHON"] = str(ROOT / ".venv/Scripts/python.exe")
    os.environ["SPARK_LOCAL_IP"] = "127.0.0.1"
    started = time.perf_counter()
    spark = (
        SparkSession.builder.master("local[2]")
        .appName("Corridor million-row feature parity")
        .config("spark.driver.memory", "2g")
        .config("spark.sql.shuffle.partitions", "8")
        .config("spark.sql.session.timeZone", "America/Toronto")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")
    try:
        trip_rows = spark.read.parquet(str(ROOT / "data/silver/fact_trip.parquet")).count()
        feature_started = time.perf_counter()
        output = (
            build_features(spark, str(ROOT / "data/silver").replace("\\", "/"))
            .select("customer_id", *FEATURES)
            .toPandas()
            .sort_values("customer_id")
            .reset_index(drop=True)
        )
        elapsed = time.perf_counter() - feature_started
        reference = (
            pd.read_parquet(ROOT / "data/gold/customer_360.parquet")
            .sort_values("customer_id")
            .reset_index(drop=True)
        )
        assert output.customer_id.equals(reference.customer_id)
        differences = {
            f: float(np.max(np.abs(output[f].to_numpy() - reference[f].to_numpy()))) for f in FEATURES
        }
        assert all(v < 1e-7 for v in differences.values()), differences
        lake = ROOT / "data/delta"
        lake.mkdir(exist_ok=True)
        delta_started = time.perf_counter()
        # Delta-rs writes transaction-log-backed tables; Spark is the feature compute engine.
        for layer in ["bronze", "silver"]:
            raw = pq.read_table(ROOT / "data" / layer / "fact_trip.parquet")
            # schema_mode: an earlier release's table at the same path has fewer columns, and a
            # plain overwrite refuses a schema change rather than replacing it.
            write_deltalake(str(lake / layer / "fact_trip"), raw, mode="overwrite", schema_mode="overwrite")
            # Bronze keeps the planted defects (duplicates, late batches), so it has its own count.
            assert (
                DeltaTable(str(lake / layer / "fact_trip")).to_pyarrow_dataset().count_rows() == raw.num_rows
            )
        write_deltalake(
            str(lake / "gold/customer_features"), output, mode="overwrite", schema_mode="overwrite"
        )
        readback = (
            DeltaTable(str(lake / "gold/customer_features"))
            .to_pandas()
            .sort_values("customer_id")
            .reset_index(drop=True)
        )
        pd.testing.assert_frame_equal(output, readback, check_dtype=False)
        receipt = {
            "status": "passed",
            "trip_rows": trip_rows,
            "customer_rows": len(output),
            "features_checked": len(FEATURES),
            "feature_seconds": elapsed,
            "delta_write_read_seconds": time.perf_counter() - delta_started,
            "total_seconds": time.perf_counter() - started,
            "spark_version": spark.version,
            "spark_master": "local[2]",
            "delta_writer": "delta-rs Python API; actual transaction logs and readback",
            "max_absolute_feature_errors": differences,
            "cloud_cost": 0,
            "execution_host": "local Windows; Java 17",
            "hosted_databricks": "Not executed",
        }
        write_json(ROOT / "outputs/spark_benchmark.json", receipt)
        print(receipt)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
