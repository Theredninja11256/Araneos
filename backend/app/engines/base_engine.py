"""
Base engine interface.

All data processing engines (pandas, Spark, etc.) must implement this
abstract class. Feature modules call this interface rather than importing
pandas or PySpark directly, which keeps the business logic engine-agnostic.

Adding a new engine in the future means:
  1. Subclass BaseEngine.
  2. Implement all abstract methods.
  3. Register it in engine_selector.py.
  — No changes needed to any feature module.
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseEngine(ABC):

    @property
    @abstractmethod
    def engine_name(self) -> str:
        """Human-readable name of this engine (e.g. 'pandas', 'spark')."""

    @abstractmethod
    def load_csv(self, file_path: str) -> Any:
        """
        Load a CSV file and return the engine's native dataframe object.
        The caller should not assume the return type — always pass it back
        into other engine methods rather than inspecting it directly.
        """

    @abstractmethod
    def get_schema(self, df: Any) -> dict[str, str]:
        """
        Return a mapping of column name → inferred data type string.
        The type strings are engine-specific but should be human-readable
        (e.g. 'int64', 'object', 'StringType').
        """

    @abstractmethod
    def get_row_count(self, df: Any) -> int:
        """Return the total number of data rows (excluding header)."""

    @abstractmethod
    def get_column_names(self, df: Any) -> list[str]:
        """Return an ordered list of column names."""

    # ── Stage 2: profiling methods ─────────────────────────────────────

    @abstractmethod
    def get_duplicate_row_count(self, df: Any) -> int:
        """Return the number of fully duplicate rows in the dataframe."""

    @abstractmethod
    def compute_column_stats(self, df: Any, col: str, row_count: int) -> dict:
        """
        Compute raw statistics for a single column and return a standardised
        dict.  The shape is IDENTICAL regardless of which engine is used —
        this contract is what allows profiling.py to be engine-agnostic.

        Keys always present
        -------------------
        is_numeric : bool
        is_string  : bool
        null_count : int
        unique_count : int
        top_values : list[dict]  — [{"value": str, "count": int}, ...]

        Keys present when is_numeric is True
        -------------------------------------
        min, max, mean, median, std : float | None
        q1, q3                      : float | None  (25th / 75th percentile)
        outlier_count               : int           (IQR method)

        Keys present when is_string is True
        ------------------------------------
        casing_inconsistency_count : int
        sample_values              : list[str]  (≤ 50 non-null values,
                                                 used for date format analysis
                                                 in profiling.py)
        """

    # ── Stage 2 helpers kept for backwards compat ──────────────────────

    def get_null_counts(self, df: Any) -> dict[str, int]:
        """Return column → null count mapping.  Implemented by each engine."""
        raise NotImplementedError(
            f"{self.engine_name} engine does not yet implement get_null_counts."
        )

    def get_basic_stats(self, df: Any, column: str) -> dict:
        """Return basic numeric stats for a column.  Implemented by each engine."""
        raise NotImplementedError(
            f"{self.engine_name} engine does not yet implement get_basic_stats."
        )
