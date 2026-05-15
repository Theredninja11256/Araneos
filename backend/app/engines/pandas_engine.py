"""
Pandas engine — the default engine for MVP and local development.

Use this engine when:
  - Running locally with small to medium datasets (up to ~1 M rows).
  - Iterating quickly during development.
  - PySpark is not installed or not required.

Set ENGINE_MODE=pandas in your .env file (this is the default).
"""

import math
from typing import Any

import pandas as pd

from .base_engine import BaseEngine


def _safe_float(val: Any) -> float | None:
    """Convert a value to a Python float, returning None for NaN or non-numeric."""
    if val is None:
        return None
    try:
        f = float(val)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


class PandasEngine(BaseEngine):

    @property
    def engine_name(self) -> str:
        return "pandas"

    def load_csv(self, file_path: str) -> pd.DataFrame:
        return pd.read_csv(file_path, low_memory=False)

    def get_schema(self, df: pd.DataFrame) -> dict[str, str]:
        return {col: str(dtype) for col, dtype in df.dtypes.items()}

    def get_row_count(self, df: pd.DataFrame) -> int:
        return len(df)

    def get_column_names(self, df: pd.DataFrame) -> list[str]:
        return df.columns.tolist()

    # ── Stage 2: profiling ─────────────────────────────────────────────

    def get_duplicate_row_count(self, df: pd.DataFrame) -> int:
        return int(df.duplicated().sum())

    def compute_column_stats(
        self, df: pd.DataFrame, col: str, row_count: int
    ) -> dict:
        """
        Compute all raw statistics for one column in a single pass.
        Returns a standardised dict — see BaseEngine.compute_column_stats for
        the full key contract.
        """
        series = df[col]
        non_null = series.dropna()

        is_numeric = pd.api.types.is_numeric_dtype(series)
        is_string = pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)

        # Top N values (exclude nulls from the count)
        top_values = [
            {"value": str(v), "count": int(c)}
            for v, c in series.value_counts(dropna=True).head(5).items()
        ]

        result: dict = {
            "is_numeric": is_numeric,
            "is_string": is_string and not is_numeric,
            "null_count": int(series.isna().sum()),
            "unique_count": int(series.nunique(dropna=True)),
            "top_values": top_values,
        }

        if is_numeric and len(non_null) > 0:
            q1 = _safe_float(non_null.quantile(0.25))
            q3 = _safe_float(non_null.quantile(0.75))

            # IQR-based outlier count
            if q1 is not None and q3 is not None:
                iqr = q3 - q1
                lower = q1 - 1.5 * iqr
                upper = q3 + 1.5 * iqr
                outlier_count = int(((non_null < lower) | (non_null > upper)).sum())
            else:
                outlier_count = 0

            result.update(
                {
                    "min": _safe_float(series.min()),
                    "max": _safe_float(series.max()),
                    "mean": _safe_float(series.mean()),
                    "median": _safe_float(series.median()),
                    "std": _safe_float(series.std()),
                    "q1": q1,
                    "q3": q3,
                    "outlier_count": outlier_count,
                }
            )
        elif is_numeric:
            # All values are null in this numeric column.
            result.update(
                {
                    "min": None, "max": None, "mean": None,
                    "median": None, "std": None,
                    "q1": None, "q3": None, "outlier_count": 0,
                }
            )

        if result["is_string"]:
            if len(non_null) > 0:
                # Detect REAL casing inconsistency: the same semantic value appears with
                # multiple case variants (e.g. "Motor", "motor", "MOTOR").
                # Simple "!= lowercase" would incorrectly flag "Active" as inconsistent.
                lower_series = non_null.str.lower()
                # Map each lowercase form → count of distinct original casings.
                variant_map = non_null.groupby(lower_series).nunique()
                # Rows where the lowercase form has >1 original spelling are affected.
                row_variants = lower_series.map(variant_map)
                casing_issues = int((row_variants > 1).sum())
            else:
                casing_issues = 0

            result["casing_inconsistency_count"] = casing_issues
            # Provide a sample of raw values for date-format analysis in profiling.py.
            result["sample_values"] = non_null.head(50).tolist()

        return result

    # ── Older helpers (kept for compatibility) ─────────────────────────

    def get_null_counts(self, df: pd.DataFrame) -> dict[str, int]:
        return df.isnull().sum().to_dict()

    def get_basic_stats(self, df: pd.DataFrame, column: str) -> dict:
        series = df[column]
        if not pd.api.types.is_numeric_dtype(series):
            return {"error": f"Column '{column}' is not numeric."}
        return {
            "min": _safe_float(series.min()),
            "max": _safe_float(series.max()),
            "mean": _safe_float(series.mean()),
            "median": _safe_float(series.median()),
            "std": _safe_float(series.std()),
        }
