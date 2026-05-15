"""
PySpark engine — the intended production-scale engine.

Use this engine when:
  - Processing large datasets (millions of rows).
  - Running in a Databricks or cluster environment.
  - You want distributed, fault-tolerant processing.

Prerequisites:
  - Java 11 or 17 must be installed: https://adoptium.net
  - Install PySpark: pip install pyspark>=3.5.0
  - Set ENGINE_MODE=spark in your .env file.

Note on startup time:
  Spark has a non-trivial JVM startup cost (~10–20 s locally).
  For rapid iteration on small files, use the pandas engine instead.

Design note:
  SparkSession is initialised lazily (only when the first method is called).
  This avoids Spark overhead when the pandas engine is selected.

Spark vs pandas differences in this implementation:
  - get_duplicate_row_count: Spark uses df.count() - df.dropDuplicates().count()
    which triggers two full scans. In production, consider caching df first.
  - compute_column_stats: each call issues several Spark jobs. For large datasets
    consider batching all column stats into a single aggregation query.
  - outlier_count: Spark uses a filter action after computing IQR bounds. This
    is a separate Spark job, unlike pandas which does it in one vectorised pass.
"""

from typing import Any

from .base_engine import BaseEngine


class SparkEngine(BaseEngine):

    def __init__(self):
        # Lazy — SparkSession is not created until first use.
        self._spark = None

    def _get_spark(self):
        """Initialise and return the shared SparkSession."""
        if self._spark is not None:
            return self._spark

        try:
            from pyspark.sql import SparkSession
        except ImportError as exc:
            raise RuntimeError(
                "PySpark is not installed. "
                "Run:  pip install pyspark>=3.5.0\n"
                "Also ensure Java 11+ is available on your PATH."
            ) from exc

        self._spark = (
            SparkSession.builder.appName("data-platform")
            .master("local[*]")
            .config("spark.ui.showConsoleProgress", "false")
            .getOrCreate()
        )
        self._spark.sparkContext.setLogLevel("WARN")
        return self._spark

    @property
    def engine_name(self) -> str:
        return "spark"

    def load_csv(self, file_path: str) -> Any:
        spark = self._get_spark()
        return (
            spark.read.option("header", True)
            .option("inferSchema", True)
            .csv(file_path)
        )

    def get_schema(self, df: Any) -> dict[str, str]:
        return {field.name: str(field.dataType) for field in df.schema.fields}

    def get_row_count(self, df: Any) -> int:
        return df.count()

    def get_column_names(self, df: Any) -> list[str]:
        return df.columns

    # ── Stage 2: profiling ─────────────────────────────────────────────

    def get_duplicate_row_count(self, df: Any) -> int:
        # Two scans — cache df before calling this if profiling many columns.
        return int(df.count() - df.dropDuplicates().count())

    def compute_column_stats(self, df: Any, col: str, row_count: int) -> dict:
        """
        Compute raw statistics for one column using Spark SQL functions.
        The returned dict matches the shape contract in BaseEngine exactly,
        so profiling.py needs no Spark-specific code.
        """
        from pyspark.sql import functions as F
        from pyspark.sql.types import NumericType, StringType

        field = next(f for f in df.schema.fields if f.name == col)
        is_numeric = isinstance(field.dataType, NumericType)
        is_string = isinstance(field.dataType, StringType)

        # ── Null count + distinct count in one Spark job ───────────────
        agg_row = df.agg(
            F.count(F.when(F.col(col).isNull(), 1)).alias("null_count"),
            F.countDistinct(col).alias("unique_count"),
        ).collect()[0]

        null_count = int(agg_row["null_count"])
        unique_count = int(agg_row["unique_count"])

        # ── Top-5 values (nulls excluded) ──────────────────────────────
        top_values = [
            {"value": str(row[col]), "count": int(row["count"])}
            for row in (
                df.filter(F.col(col).isNotNull())
                .groupBy(col)
                .count()
                .orderBy(F.desc("count"))
                .limit(5)
                .collect()
            )
        ]

        result: dict = {
            "is_numeric": is_numeric,
            "is_string": is_string and not is_numeric,
            "null_count": null_count,
            "unique_count": unique_count,
            "top_values": top_values,
        }

        if is_numeric:
            stats_row = df.select(
                F.min(col).alias("min"),
                F.max(col).alias("max"),
                F.mean(col).alias("mean"),
                F.percentile_approx(col, 0.5).alias("median"),
                F.stddev(col).alias("std"),
                F.percentile_approx(col, 0.25).alias("q1"),
                F.percentile_approx(col, 0.75).alias("q3"),
            ).collect()[0]

            def _sf(v: Any) -> float | None:
                return float(v) if v is not None else None

            q1 = _sf(stats_row["q1"])
            q3 = _sf(stats_row["q3"])

            if q1 is not None and q3 is not None:
                iqr = q3 - q1
                lower = q1 - 1.5 * iqr
                upper = q3 + 1.5 * iqr
                outlier_count = int(
                    df.filter(
                        F.col(col).isNotNull()
                        & ((F.col(col) < lower) | (F.col(col) > upper))
                    ).count()
                )
            else:
                outlier_count = 0

            result.update(
                {
                    "min": _sf(stats_row["min"]),
                    "max": _sf(stats_row["max"]),
                    "mean": _sf(stats_row["mean"]),
                    "median": _sf(stats_row["median"]),
                    "std": _sf(stats_row["std"]),
                    "q1": q1,
                    "q3": q3,
                    "outlier_count": outlier_count,
                }
            )

        if is_string:
            # Detect real casing inconsistency: the same lowercase form appears
            # with >1 distinct original casing.  (Mirrors the pandas engine logic.)
            df_lower = df.select(
                F.col(col).alias("_orig"),
                F.lower(F.col(col)).alias("_lower"),
            ).filter(F.col("_orig").isNotNull())

            variant_counts = df_lower.groupBy("_lower").agg(
                F.countDistinct("_orig").alias("variants")
            )
            casing_count = int(
                df_lower.join(variant_counts, on="_lower")
                .filter(F.col("variants") > 1)
                .count()
            )
            result["casing_inconsistency_count"] = casing_count

            # Collect a small sample for date-format analysis in profiling.py.
            sample_rows = (
                df.select(col)
                .filter(F.col(col).isNotNull())
                .limit(50)
                .collect()
            )
            result["sample_values"] = [row[col] for row in sample_rows]

        return result

    # ── Older helpers (kept for compatibility) ─────────────────────────

    def get_null_counts(self, df: Any) -> dict[str, int]:
        from pyspark.sql import functions as F

        null_counts = df.select(
            [F.count(F.when(F.col(c).isNull(), c)).alias(c) for c in df.columns]
        ).collect()[0]
        return {col: null_counts[col] for col in df.columns}

    def get_basic_stats(self, df: Any, column: str) -> dict:
        from pyspark.sql import functions as F

        row = df.select(
            F.min(column).alias("min"),
            F.max(column).alias("max"),
            F.mean(column).alias("mean"),
            F.percentile_approx(column, 0.5).alias("median"),
            F.stddev(column).alias("std"),
        ).collect()[0]

        def _sf(v: Any) -> float | None:
            return float(v) if v is not None else None

        return {
            "min": _sf(row["min"]),
            "max": _sf(row["max"]),
            "mean": _sf(row["mean"]),
            "median": _sf(row["median"]),
            "std": _sf(row["std"]),
        }
