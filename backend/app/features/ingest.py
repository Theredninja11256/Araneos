"""
Feature: Dataset Ingestion

Handles loading an uploaded file through the configured processing engine
and returning a standardised metadata dictionary.

This is the first feature module in the pipeline. In Stage 2 it will be
extended to pass the loaded dataframe directly into the profiling module.

Returned metadata shape (same regardless of engine):
{
    "engine_used":    str,        — e.g. "pandas" or "spark"
    "file_name":      str,        — basename of the saved file
    "file_path":      str,        — absolute or relative path on disk
    "row_count":      int,        — number of data rows
    "column_count":   int,        — number of columns
    "columns":        list[str],  — ordered column names
    "schema":         dict,       — col → inferred type string
}
"""

from pathlib import Path

from app.engines.engine_selector import get_engine


def load_file(file_path: str) -> dict:
    """
    Load a saved file through the active engine and return basic metadata.

    Args:
        file_path: Path to the file on disk (already saved by the upload route).

    Returns:
        Standardised metadata dictionary. Schema is identical regardless of
        whether pandas or Spark was used to load the file.
    """
    engine = get_engine()
    df = engine.load_csv(file_path)

    columns = engine.get_column_names(df)

    return {
        "engine_used": engine.engine_name,
        "file_name": Path(file_path).name,
        "file_path": file_path,
        "row_count": engine.get_row_count(df),
        "column_count": len(columns),
        "columns": columns,
        "schema": engine.get_schema(df),
    }
