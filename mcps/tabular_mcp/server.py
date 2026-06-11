"""
MCP Server for Tabular Data Analysis.

Provides tools for:
- Dataset description and statistics
- Anomaly detection
- Correlation computation
- Row filtering
- SQLite querying
- Pivot tables
- Data quality reports
- Time series analysis
- Chart generation
- Dataset merging
- Statistical testing
- Auto-insights
- Data export
"""

import base64
import io
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for server use
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from mcp.server.fastmcp import FastMCP
from scipy import stats

# Initialize MCP server
mcp = FastMCP(
    "Tabular Data Analysis",
    dependencies=["pandas", "numpy", "scipy"],
)

# Store loaded datasets in memory for efficient re-use
_datasets: dict[str, pd.DataFrame] = {}

# Get project root directory (parent of src/)
_PROJECT_ROOT = Path(__file__).parent.parent


def _resolve_path(file_path: str) -> Path:
    """
    Resolve file path relative to project root if it's a relative path.
    
    Args:
        file_path: Absolute or relative file path
    
    Returns:
        Resolved absolute Path
    """
    path = Path(file_path)
    
    # If absolute path, use as-is
    if path.is_absolute():
        return path
    
    # Otherwise, resolve relative to project root
    resolved = _PROJECT_ROOT / path
    return resolved.resolve()

# An Internal Helper (Hidden from the LLM/Client) : function name with "_" at start
def _load_data(file_path: str) -> pd.DataFrame:
    """Load data from CSV or SQLite file."""
    path = _resolve_path(file_path)
    
    if not path.exists():
        raise FileNotFoundError(
            f"File not found: {file_path}\n"
            f"Resolved to: {path}\n"
            f"Project root: {_PROJECT_ROOT}\n"
            f"Current working directory: {Path.cwd()}"
        )
    
    suffix = path.suffix.lower()
    
    if suffix == ".csv":
        return pd.read_csv(str(path))
    elif suffix in (".db", ".sqlite", ".sqlite3"):
        # For SQLite, list tables or load first table
        conn = sqlite3.connect(str(path))
        tables = pd.read_sql_query(
            "SELECT name FROM sqlite_master WHERE type='table'", conn
        )
        if tables.empty:
            conn.close()
            raise ValueError(f"No tables found in SQLite database: {file_path}")
        first_table = tables.iloc[0]["name"]
        df = pd.read_sql_query(f"SELECT * FROM {first_table}", conn)
        conn.close()
        return df
    else:
        raise ValueError(f"Unsupported file format: {suffix}. Use .csv or .db/.sqlite")


def _get_numeric_columns(df: pd.DataFrame) -> list[str]:
    """Get list of numeric column names."""
    return df.select_dtypes(include=[np.number]).columns.tolist()


@mcp.tool()
def describe_dataset(file_path: str, include_all: bool = False) -> dict[str, Any]:
    """
    Generate comprehensive statistics for a tabular dataset.
    
    Args:
        file_path: Path to CSV or SQLite file
        include_all: If True, include statistics for all columns (not just numeric)
    
    Returns:
        Dictionary containing:
        - shape: (rows, columns)
        - columns: List of column names with their types
        - numeric_stats: Descriptive statistics for numeric columns
        - missing_values: Count of missing values per column
        - sample: First 5 rows as preview
    """
    df = _load_data(file_path)
    
    # Basic info
    result = {
        "shape": {"rows": len(df), "columns": len(df.columns)},
        "columns": {
            col: str(df[col].dtype) for col in df.columns
        },
        "missing_values": df.isnull().sum().to_dict(),
    }
    
    # Numeric statistics
    numeric_cols = _get_numeric_columns(df)
    if numeric_cols:
        stats_df = df[numeric_cols].describe()
        # Add additional stats
        stats_df.loc["median"] = df[numeric_cols].median()
        stats_df.loc["skew"] = df[numeric_cols].skew()
        stats_df.loc["kurtosis"] = df[numeric_cols].kurtosis()
        result["numeric_stats"] = stats_df.to_dict()
    
    # Categorical columns info
    cat_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()
    if cat_cols:
        result["categorical_columns"] = {
            col: {
                "unique_values": df[col].nunique(),
                "top_values": df[col].value_counts().head(5).to_dict()
            }
            for col in cat_cols
        }
    
    # Sample data
    result["sample"] = df.head(5).to_dict(orient="records")
    
    return result


@mcp.tool()
def detect_anomalies(
    file_path: str,
    column: str,
    method: str = "zscore",
    threshold: float = 3.0,
) -> dict[str, Any]:
    """
    Detect anomalies/outliers in a numeric column.
    
    Args:
        file_path: Path to CSV or SQLite file
        column: Name of the numeric column to analyze
        method: Detection method - 'zscore' (default), 'iqr', or 'isolation_forest'
        threshold: Threshold for anomaly detection (default 3.0 for zscore, 1.5 for IQR)
    
    Returns:
        Dictionary containing:
        - method: Detection method used
        - anomaly_count: Number of anomalies found
        - anomaly_indices: Row indices of anomalies
        - anomalies: The anomalous rows
        - statistics: Column statistics
    """
    df = _load_data(file_path)
    
    if column not in df.columns:
        raise ValueError(f"Column '{column}' not found. Available: {df.columns.tolist()}")
    
    if not np.issubdtype(df[column].dtype, np.number):
        raise ValueError(f"Column '{column}' is not numeric")
    
    col_data = df[column].dropna()
    
    if method == "zscore":
        # Z-score method
        z_scores = np.abs(stats.zscore(col_data))
        anomaly_mask = z_scores > threshold
        anomaly_indices = col_data[anomaly_mask].index.tolist()
        
    elif method == "iqr":
        # Interquartile Range method
        q1 = col_data.quantile(0.25)
        q3 = col_data.quantile(0.75)
        iqr = q3 - q1
        lower_bound = q1 - threshold * iqr
        upper_bound = q3 + threshold * iqr
        anomaly_mask = (col_data < lower_bound) | (col_data > upper_bound)
        anomaly_indices = col_data[anomaly_mask].index.tolist()
        
    else:
        raise ValueError(f"Unknown method: {method}. Use 'zscore' or 'iqr'")
    
    anomalies_df = df.loc[anomaly_indices]
    
    return {
        "method": method,
        "threshold": threshold,
        "column": column,
        "anomaly_count": len(anomaly_indices),
        "anomaly_percentage": round(len(anomaly_indices) / len(col_data) * 100, 2),
        "anomaly_indices": anomaly_indices,
        "anomalies": anomalies_df.to_dict(orient="records"),
        "statistics": {
            "mean": float(col_data.mean()),
            "std": float(col_data.std()),
            "min": float(col_data.min()),
            "max": float(col_data.max()),
            "median": float(col_data.median()),
        }
    }


@mcp.tool()
def compute_correlation(
    file_path: str,
    columns: list[str] | None = None,
    method: str = "pearson",
) -> dict[str, Any]:
    """
    Compute correlation matrix between numeric columns.
    
    Args:
        file_path: Path to CSV or SQLite file
        columns: List of columns to include (default: all numeric columns)
        method: Correlation method - 'pearson' (default), 'spearman', or 'kendall'
    
    Returns:
        Dictionary containing:
        - method: Correlation method used
        - correlation_matrix: Full correlation matrix
        - top_correlations: Top 10 strongest correlations (excluding self-correlations)
    """
    df = _load_data(file_path)
    
    # Get numeric columns
    if columns:
        # Validate provided columns
        invalid = [c for c in columns if c not in df.columns]
        if invalid:
            raise ValueError(f"Columns not found: {invalid}")
        numeric_df = df[columns].select_dtypes(include=[np.number])
    else:
        numeric_df = df.select_dtypes(include=[np.number])
    
    if len(numeric_df.columns) < 2:
        raise ValueError("Need at least 2 numeric columns for correlation")
    
    # Compute correlation matrix
    corr_matrix = numeric_df.corr(method=method)
    
    # Find top correlations (excluding diagonal)
    correlations = []
    for i, col1 in enumerate(corr_matrix.columns):
        for j, col2 in enumerate(corr_matrix.columns):
            if i < j:  # Upper triangle only
                corr_value = corr_matrix.loc[col1, col2]
                if not np.isnan(corr_value):
                    correlations.append({
                        "column1": col1,
                        "column2": col2,
                        "correlation": round(float(corr_value), 4),
                        "strength": _interpret_correlation(abs(corr_value))
                    })
    
    # Sort by absolute correlation
    correlations.sort(key=lambda x: abs(x["correlation"]), reverse=True)
    
    return {
        "method": method,
        "columns_analyzed": corr_matrix.columns.tolist(),
        "correlation_matrix": corr_matrix.round(4).to_dict(),
        "top_correlations": correlations[:10],
    }


def _interpret_correlation(value: float) -> str:
    """Interpret correlation strength."""
    if value >= 0.9:
        return "very_strong"
    elif value >= 0.7:
        return "strong"
    elif value >= 0.5:
        return "moderate"
    elif value >= 0.3:
        return "weak"
    else:
        return "negligible"


@mcp.tool()
def filter_rows(
    file_path: str,
    column: str,
    operator: str,
    value: str | float | int,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Filter rows based on a condition.
    
    Args:
        file_path: Path to CSV or SQLite file
        column: Column name to filter on
        operator: Comparison operator - 'eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'contains', 'startswith', 'endswith'
        value: Value to compare against
        limit: Maximum number of rows to return (default 100)
    
    Returns:
        Dictionary containing:
        - filter_applied: Description of the filter
        - original_count: Number of rows before filtering
        - filtered_count: Number of rows after filtering
        - rows: Filtered rows (up to limit)
    """
    df = _load_data(file_path)
    
    if column not in df.columns:
        raise ValueError(f"Column '{column}' not found. Available: {df.columns.tolist()}")
    
    original_count = len(df)
    
    # Apply filter based on operator
    if operator == "eq":
        mask = df[column] == value
    elif operator == "ne":
        mask = df[column] != value
    elif operator == "gt":
        mask = df[column] > float(value)
    elif operator == "gte":
        mask = df[column] >= float(value)
    elif operator == "lt":
        mask = df[column] < float(value)
    elif operator == "lte":
        mask = df[column] <= float(value)
    elif operator == "contains":
        mask = df[column].astype(str).str.contains(str(value), case=False, na=False)
    elif operator == "startswith":
        mask = df[column].astype(str).str.startswith(str(value), na=False)
    elif operator == "endswith":
        mask = df[column].astype(str).str.endswith(str(value), na=False)
    else:
        raise ValueError(
            f"Unknown operator: {operator}. Use: eq, ne, gt, gte, lt, lte, contains, startswith, endswith"
        )
    
    filtered_df = df[mask]
    
    return {
        "filter_applied": f"{column} {operator} {value}",
        "original_count": original_count,
        "filtered_count": len(filtered_df),
        "rows": filtered_df.head(limit).to_dict(orient="records"),
        "truncated": len(filtered_df) > limit,
    }


@mcp.tool()
def query_sqlite(
    db_path: str,
    query: str,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Execute a SQL query on a SQLite database.
    
    Args:
        db_path: Path to SQLite database file
        query: SQL query to execute (SELECT queries only for safety)
        limit: Maximum number of rows to return (default 100)
    
    Returns:
        Dictionary containing:
        - query: The executed query
        - row_count: Number of rows returned
        - columns: List of column names
        - rows: Query results
    """
    # Basic safety check - only allow SELECT
    query_upper = query.strip().upper()
    if not query_upper.startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed for safety")
    
    path = _resolve_path(db_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Database not found: {db_path}\n"
            f"Resolved to: {path}\n"
            f"Project root: {_PROJECT_ROOT}"
        )
    
    conn = sqlite3.connect(str(path))
    try:
        # Add LIMIT if not present
        if "LIMIT" not in query_upper:
            query = f"{query.rstrip(';')} LIMIT {limit}"
        
        df = pd.read_sql_query(query, conn)
        
        return {
            "query": query,
            "row_count": len(df),
            "columns": df.columns.tolist(),
            "rows": df.to_dict(orient="records"),
        }
    finally:
        conn.close()


@mcp.tool()
def list_tables(db_path: str) -> dict[str, Any]:
    """
    List all tables in a SQLite database.
    
    Args:
        db_path: Path to SQLite database file
    
    Returns:
        Dictionary containing table names and their schemas
    """
    path = _resolve_path(db_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Database not found: {db_path}\n"
            f"Resolved to: {path}\n"
            f"Project root: {_PROJECT_ROOT}"
        )
    
    conn = sqlite3.connect(str(path))
    try:
        # Get table names
        tables = pd.read_sql_query(
            "SELECT name FROM sqlite_master WHERE type='table'", conn
        )
        
        result = {"tables": {}}
        
        for table_name in tables["name"]:
            # Get schema for each table
            schema = pd.read_sql_query(
                f"PRAGMA table_info({table_name})", conn
            )
            
            # Get row count
            count = pd.read_sql_query(
                f"SELECT COUNT(*) as cnt FROM {table_name}", conn
            ).iloc[0]["cnt"]
            
            result["tables"][table_name] = {
                "row_count": int(count),
                "columns": [
                    {
                        "name": row["name"],
                        "type": row["type"],
                        "nullable": not row["notnull"],
                        "primary_key": bool(row["pk"]),
                    }
                    for _, row in schema.iterrows()
                ]
            }
        
        return result
    finally:
        conn.close()


@mcp.tool()
def group_aggregate(
    file_path: str,
    group_by: list[str],
    aggregations: dict[str, list[str]],
) -> dict[str, Any]:
    """
    Group data and compute aggregations.
    
    Args:
        file_path: Path to CSV or SQLite file
        group_by: Columns to group by
        aggregations: Dictionary mapping column names to list of aggregation functions
                     (e.g., {"sales": ["sum", "mean"], "quantity": ["count", "max"]})
                     Supported: sum, mean, median, min, max, count, std, var
    
    Returns:
        Dictionary containing grouped and aggregated data
    """
    df = _load_data(file_path)
    
    # Validate group_by columns
    invalid = [c for c in group_by if c not in df.columns]
    if invalid:
        raise ValueError(f"Group-by columns not found: {invalid}")
    
    # Validate aggregation columns
    for col in aggregations:
        if col not in df.columns:
            raise ValueError(f"Aggregation column '{col}' not found")
    
    # Perform groupby
    grouped = df.groupby(group_by).agg(aggregations)
    
    # Flatten column names
    grouped.columns = ["_".join(col).strip() for col in grouped.columns]
    grouped = grouped.reset_index()
    
    return {
        "group_by": group_by,
        "aggregations": aggregations,
        "group_count": len(grouped),
        "result": grouped.to_dict(orient="records"),
    }


@mcp.tool()
def list_data_files(data_dir: str = "data") -> dict[str, Any]:
    """
    List available data files in the project data directory.
    
    Args:
        data_dir: Relative path to data directory (default: "data")
    
    Returns:
        Dictionary containing list of available CSV and SQLite files
    """
    data_path = _resolve_path(data_dir)
    
    if not data_path.exists():
        return {
            "data_directory": str(data_path),
            "exists": False,
            "files": []
        }
    
    csv_files = []
    db_files = []
    
    for file_path in sorted(data_path.iterdir()):
        if file_path.is_file():
            suffix = file_path.suffix.lower()
            file_info = {
                "name": file_path.name,
                "path": str(file_path.relative_to(_PROJECT_ROOT)),
                "size_bytes": file_path.stat().st_size,
            }
            
            if suffix == ".csv":
                # Try to get basic info about CSV
                try:
                    df = pd.read_csv(str(file_path), nrows=0)
                    file_info["columns"] = df.columns.tolist()
                    file_info["column_count"] = len(df.columns)
                except Exception:
                    pass
                csv_files.append(file_info)
            elif suffix in (".db", ".sqlite", ".sqlite3"):
                db_files.append(file_info)
    
    return {
        "data_directory": str(data_path.relative_to(_PROJECT_ROOT)),
        "absolute_path": str(data_path),
        "csv_files": csv_files,
        "sqlite_files": db_files,
        "total_files": len(csv_files) + len(db_files),
    }


# ============================================================================
# NEW TOOLS: Advanced Analytics & Visualization
# ============================================================================


@mcp.tool()
def create_pivot_table(
    file_path: str,
    index: list[str],
    columns: list[str] | None = None,
    values: str | None = None,
    aggfunc: str = "mean",
    fill_value: float | None = None,
) -> dict[str, Any]:
    """
    Create a pivot table from tabular data - the most common business analysis operation.
    
    Args:
        file_path: Path to CSV or SQLite file
        index: Column(s) to use as row labels (grouping)
        columns: Column(s) to use as column headers (optional)
        values: Column to aggregate (default: first numeric column)
        aggfunc: Aggregation function - 'sum', 'mean', 'count', 'min', 'max', 'median', 'std'
        fill_value: Value to replace missing entries (default: None = show as null)
    
    Returns:
        Dictionary containing the pivot table data and metadata
    
    Example:
        create_pivot_table(
            file_path="data/sales.csv",
            index=["region"],
            columns=["category"],
            values="revenue",
            aggfunc="sum"
        )
    """
    df = _load_data(file_path)
    
    # Validate index columns
    invalid = [c for c in index if c not in df.columns]
    if invalid:
        raise ValueError(f"Index columns not found: {invalid}. Available: {df.columns.tolist()}")
    
    # Validate columns if provided
    if columns:
        invalid = [c for c in columns if c not in df.columns]
        if invalid:
            raise ValueError(f"Column headers not found: {invalid}")
    
    # Default to first numeric column if values not specified
    if values is None:
        numeric_cols = _get_numeric_columns(df)
        if not numeric_cols:
            raise ValueError("No numeric columns found for aggregation")
        values = numeric_cols[0]
    elif values not in df.columns:
        raise ValueError(f"Values column '{values}' not found")
    
    # Map aggfunc string to function
    agg_map = {
        "sum": "sum",
        "mean": "mean",
        "count": "count",
        "min": "min",
        "max": "max",
        "median": "median",
        "std": "std",
    }
    if aggfunc not in agg_map:
        raise ValueError(f"Unknown aggfunc: {aggfunc}. Use: {list(agg_map.keys())}")
    
    # Create pivot table
    pivot = pd.pivot_table(
        df,
        values=values,
        index=index,
        columns=columns,
        aggfunc=agg_map[aggfunc],
        fill_value=fill_value,
    )
    
    # Reset index for cleaner output
    pivot_reset = pivot.reset_index()
    
    return {
        "index": index,
        "columns": columns,
        "values": values,
        "aggfunc": aggfunc,
        "shape": {"rows": len(pivot), "columns": len(pivot.columns)},
        "pivot_table": pivot_reset.to_dict(orient="records"),
        "summary": {
            "total": float(pivot.values.sum()) if np.issubdtype(pivot.values.dtype, np.number) else None,
            "grand_mean": float(pivot.values.mean()) if np.issubdtype(pivot.values.dtype, np.number) else None,
        }
    }


@mcp.tool()
def data_quality_report(file_path: str) -> dict[str, Any]:
    """
    Generate a comprehensive data quality assessment report.
    Essential for understanding data health before analysis.
    
    Args:
        file_path: Path to CSV or SQLite file
    
    Returns:
        Dictionary containing:
        - completeness: Missing value analysis per column
        - uniqueness: Duplicate detection
        - validity: Data type consistency and outlier counts
        - overall_score: Data quality score (0-100)
    """
    df = _load_data(file_path)
    
    total_cells = df.size
    total_rows = len(df)
    
    # Completeness Analysis
    missing_per_column = df.isnull().sum().to_dict()
    missing_pct_per_column = (df.isnull().sum() / total_rows * 100).round(2).to_dict()
    total_missing = df.isnull().sum().sum()
    completeness_score = 100 - (total_missing / total_cells * 100)
    
    # Uniqueness Analysis
    duplicate_rows = df.duplicated().sum()
    duplicate_pct = (duplicate_rows / total_rows * 100) if total_rows > 0 else 0
    uniqueness_score = 100 - duplicate_pct
    
    # Column-level uniqueness
    column_uniqueness = {
        col: {
            "unique_count": df[col].nunique(),
            "unique_pct": round(df[col].nunique() / total_rows * 100, 2) if total_rows > 0 else 0,
            "is_potential_id": df[col].nunique() == total_rows,
        }
        for col in df.columns
    }
    
    # Validity Analysis
    validity_issues = []
    numeric_cols = _get_numeric_columns(df)
    
    for col in numeric_cols:
        col_data = df[col].dropna()
        if len(col_data) > 0:
            # Check for outliers using IQR
            q1, q3 = col_data.quantile([0.25, 0.75])
            iqr = q3 - q1
            outlier_count = ((col_data < q1 - 1.5 * iqr) | (col_data > q3 + 1.5 * iqr)).sum()
            if outlier_count > 0:
                validity_issues.append({
                    "column": col,
                    "issue": "outliers",
                    "count": int(outlier_count),
                    "pct": round(outlier_count / len(col_data) * 100, 2),
                })
            
            # Check for negative values in typically positive columns
            if col_data.min() < 0:
                neg_count = (col_data < 0).sum()
                validity_issues.append({
                    "column": col,
                    "issue": "negative_values",
                    "count": int(neg_count),
                    "min_value": float(col_data.min()),
                })
    
    # Check for empty strings in text columns
    text_cols = df.select_dtypes(include=["object"]).columns
    for col in text_cols:
        empty_strings = (df[col] == "").sum()
        if empty_strings > 0:
            validity_issues.append({
                "column": col,
                "issue": "empty_strings",
                "count": int(empty_strings),
            })
    
    validity_score = max(0, 100 - len(validity_issues) * 5)
    
    # Overall Data Quality Score
    overall_score = round((completeness_score * 0.4 + uniqueness_score * 0.3 + validity_score * 0.3), 1)
    
    # Quality grade
    if overall_score >= 90:
        grade = "A"
        recommendation = "Excellent data quality. Ready for analysis."
    elif overall_score >= 80:
        grade = "B"
        recommendation = "Good data quality. Minor cleaning recommended."
    elif overall_score >= 70:
        grade = "C"
        recommendation = "Moderate data quality. Cleaning needed before analysis."
    elif overall_score >= 60:
        grade = "D"
        recommendation = "Poor data quality. Significant cleaning required."
    else:
        grade = "F"
        recommendation = "Critical data quality issues. Major data cleaning needed."
    
    return {
        "file": file_path,
        "shape": {"rows": total_rows, "columns": len(df.columns)},
        "overall_quality": {
            "score": overall_score,
            "grade": grade,
            "recommendation": recommendation,
        },
        "completeness": {
            "score": round(completeness_score, 1),
            "total_missing_cells": int(total_missing),
            "missing_by_column": missing_per_column,
            "missing_pct_by_column": missing_pct_per_column,
            "columns_with_missing": [col for col, pct in missing_pct_per_column.items() if pct > 0],
        },
        "uniqueness": {
            "score": round(uniqueness_score, 1),
            "duplicate_rows": int(duplicate_rows),
            "duplicate_pct": round(duplicate_pct, 2),
            "column_uniqueness": column_uniqueness,
        },
        "validity": {
            "score": validity_score,
            "issues": validity_issues,
        },
    }


@mcp.tool()
def analyze_time_series(
    file_path: str,
    date_column: str,
    value_column: str,
    freq: str = "D",
    include_forecast: bool = False,
) -> dict[str, Any]:
    """
    Perform time series analysis including trend detection, seasonality, and statistics.
    
    Args:
        file_path: Path to CSV or SQLite file
        date_column: Name of the date/datetime column
        value_column: Name of the numeric column to analyze
        freq: Frequency for resampling - 'D' (daily), 'W' (weekly), 'M' (monthly), 'Q' (quarterly), 'Y' (yearly)
        include_forecast: If True, include simple moving average forecast
    
    Returns:
        Dictionary containing:
        - trend: Overall trend direction and statistics
        - statistics: Time series statistics
        - moving_averages: 7, 30, 90 period moving averages
        - seasonality: Day of week / month patterns
        - forecast: Simple forecast if requested
    """
    df = _load_data(file_path)
    
    if date_column not in df.columns:
        raise ValueError(f"Date column '{date_column}' not found. Available: {df.columns.tolist()}")
    if value_column not in df.columns:
        raise ValueError(f"Value column '{value_column}' not found")
    
    # Parse dates
    df[date_column] = pd.to_datetime(df[date_column], errors='coerce')
    df = df.dropna(subset=[date_column, value_column])
    df = df.sort_values(date_column)
    
    # Create time series
    ts = df.set_index(date_column)[value_column]
    
    if len(ts) < 3:
        raise ValueError("Need at least 3 data points for time series analysis")
    
    # Basic statistics
    date_range = {
        "start": str(ts.index.min().date()),
        "end": str(ts.index.max().date()),
        "periods": len(ts),
        "span_days": (ts.index.max() - ts.index.min()).days,
    }
    
    # Trend analysis using linear regression
    x = np.arange(len(ts))
    slope, intercept, r_value, p_value, std_err = stats.linregress(x, ts.values)
    
    trend_direction = "increasing" if slope > 0 else "decreasing" if slope < 0 else "flat"
    trend_strength = abs(r_value)
    
    trend = {
        "direction": trend_direction,
        "slope": round(float(slope), 4),
        "r_squared": round(float(r_value ** 2), 4),
        "strength": "strong" if trend_strength > 0.7 else "moderate" if trend_strength > 0.4 else "weak",
        "pct_change_total": round(float((ts.iloc[-1] - ts.iloc[0]) / ts.iloc[0] * 100), 2) if ts.iloc[0] != 0 else None,
    }
    
    # Calculate moving averages
    ma_result = {}
    for window in [7, 30, 90]:
        if len(ts) >= window:
            ma = ts.rolling(window=window).mean()
            ma_result[f"ma_{window}"] = {
                "current": round(float(ma.iloc[-1]), 2) if not pd.isna(ma.iloc[-1]) else None,
                "min": round(float(ma.min()), 2),
                "max": round(float(ma.max()), 2),
            }
    
    # Resample by frequency
    resampled = ts.resample(freq).agg(['mean', 'sum', 'count', 'min', 'max'])
    
    # Seasonality analysis (if enough data)
    seasonality = {}
    if len(df) >= 7:
        df['dow'] = df[date_column].dt.day_name()
        dow_stats = df.groupby('dow')[value_column].mean().reindex([
            'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'
        ])
        seasonality['day_of_week'] = dow_stats.round(2).to_dict()
        
        best_day = dow_stats.idxmax()
        worst_day = dow_stats.idxmin()
        seasonality['insights'] = {
            'best_day': best_day,
            'worst_day': worst_day,
            'variation_pct': round(float((dow_stats.max() - dow_stats.min()) / dow_stats.mean() * 100), 1) if dow_stats.mean() != 0 else 0,
        }
    
    if len(df) >= 30:
        df['month'] = df[date_column].dt.month_name()
        month_stats = df.groupby('month')[value_column].mean()
        seasonality['monthly'] = month_stats.round(2).to_dict()
    
    # Statistics
    statistics = {
        "mean": round(float(ts.mean()), 2),
        "median": round(float(ts.median()), 2),
        "std": round(float(ts.std()), 2),
        "min": round(float(ts.min()), 2),
        "max": round(float(ts.max()), 2),
        "volatility": round(float(ts.std() / ts.mean() * 100), 2) if ts.mean() != 0 else 0,
    }
    
    # Simple forecast using moving average
    forecast = None
    if include_forecast and len(ts) >= 7:
        forecast_window = min(7, len(ts))
        forecast_value = ts.tail(forecast_window).mean()
        forecast = {
            "method": f"{forecast_window}-period moving average",
            "next_period_estimate": round(float(forecast_value), 2),
            "confidence_note": "Simple estimate based on recent average",
        }
    
    # Recent data sample
    recent_data = ts.tail(10).reset_index()
    recent_data.columns = ['date', 'value']
    recent_data['date'] = recent_data['date'].dt.strftime('%Y-%m-%d')
    
    return {
        "date_column": date_column,
        "value_column": value_column,
        "date_range": date_range,
        "trend": trend,
        "statistics": statistics,
        "moving_averages": ma_result,
        "seasonality": seasonality,
        "resampled_by": freq,
        "resampled_periods": len(resampled),
        "forecast": forecast,
        "recent_data": recent_data.to_dict(orient='records'),
    }


@mcp.tool()
def generate_chart(
    file_path: str,
    chart_type: str,
    x_column: str | None = None,
    y_column: str | None = None,
    group_by: str | None = None,
    title: str | None = None,
    output_format: str = "base64",
) -> dict[str, Any]:
    """
    Generate a chart/visualization from tabular data.
    Returns chart as base64-encoded PNG for display.
    
    Args:
        file_path: Path to CSV or SQLite file
        chart_type: Type of chart - 'bar', 'line', 'scatter', 'histogram', 'pie', 'box'
        x_column: Column for X-axis (not needed for histogram/pie)
        y_column: Column for Y-axis values
        group_by: Optional column for grouping/coloring
        title: Chart title (auto-generated if not provided)
        output_format: 'base64' (default) or 'file' (saves to data/charts/)
    
    Returns:
        Dictionary containing chart data as base64 or file path
    """
    df = _load_data(file_path)
    
    valid_types = ['bar', 'line', 'scatter', 'histogram', 'pie', 'box']
    if chart_type not in valid_types:
        raise ValueError(f"Unknown chart_type: {chart_type}. Use: {valid_types}")
    
    # Set up the figure with a clean style
    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Generate chart based on type
    if chart_type == 'histogram':
        if y_column is None:
            numeric_cols = _get_numeric_columns(df)
            if not numeric_cols:
                raise ValueError("No numeric columns found for histogram")
            y_column = numeric_cols[0]
        
        ax.hist(df[y_column].dropna(), bins=30, edgecolor='black', alpha=0.7, color='#4C72B0')
        ax.set_xlabel(y_column)
        ax.set_ylabel('Frequency')
        auto_title = f'Distribution of {y_column}'
        
    elif chart_type == 'pie':
        if x_column is None:
            cat_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
            if not cat_cols:
                raise ValueError("No categorical columns found for pie chart")
            x_column = cat_cols[0]
        
        value_counts = df[x_column].value_counts().head(10)
        colors = plt.cm.Set3(np.linspace(0, 1, len(value_counts)))
        ax.pie(value_counts.values, labels=value_counts.index, autopct='%1.1f%%', colors=colors)
        auto_title = f'Distribution of {x_column}'
        
    elif chart_type == 'box':
        if y_column is None:
            numeric_cols = _get_numeric_columns(df)
            if not numeric_cols:
                raise ValueError("No numeric columns found for box plot")
            y_column = numeric_cols[0]
        
        if group_by and group_by in df.columns:
            groups = df[group_by].unique()[:10]  # Limit to 10 groups
            data = [df[df[group_by] == g][y_column].dropna() for g in groups]
            ax.boxplot(data, labels=groups)
            ax.set_xlabel(group_by)
        else:
            ax.boxplot(df[y_column].dropna())
        ax.set_ylabel(y_column)
        auto_title = f'Box Plot of {y_column}'
        
    elif chart_type in ['bar', 'line', 'scatter']:
        if x_column is None or y_column is None:
            raise ValueError(f"Both x_column and y_column are required for {chart_type} chart")
        
        if x_column not in df.columns:
            raise ValueError(f"x_column '{x_column}' not found")
        if y_column not in df.columns:
            raise ValueError(f"y_column '{y_column}' not found")
        
        if group_by and group_by in df.columns:
            for name, group in df.groupby(group_by):
                if chart_type == 'bar':
                    ax.bar(group[x_column].astype(str), group[y_column], label=str(name), alpha=0.7)
                elif chart_type == 'line':
                    ax.plot(group[x_column], group[y_column], label=str(name), marker='o', markersize=4)
                else:  # scatter
                    ax.scatter(group[x_column], group[y_column], label=str(name), alpha=0.7)
            ax.legend(title=group_by, loc='best')
        else:
            if chart_type == 'bar':
                # For bar charts, aggregate if needed
                if df[x_column].dtype == 'object':
                    agg = df.groupby(x_column)[y_column].mean()
                    ax.bar(agg.index.astype(str), agg.values, color='#4C72B0', alpha=0.7)
                else:
                    ax.bar(df[x_column].astype(str).head(50), df[y_column].head(50), color='#4C72B0', alpha=0.7)
            elif chart_type == 'line':
                ax.plot(df[x_column], df[y_column], marker='o', markersize=4, color='#4C72B0')
            else:  # scatter
                ax.scatter(df[x_column], df[y_column], alpha=0.6, color='#4C72B0')
        
        ax.set_xlabel(x_column)
        ax.set_ylabel(y_column)
        auto_title = f'{y_column} by {x_column}'
        
        # Rotate x labels if needed
        if df[x_column].dtype == 'object' or chart_type == 'bar':
            plt.xticks(rotation=45, ha='right')
    
    # Set title
    ax.set_title(title or auto_title, fontsize=14, fontweight='bold')
    
    plt.tight_layout()
    
    # Save chart
    if output_format == 'file':
        charts_dir = _PROJECT_ROOT / 'data' / 'charts'
        charts_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'{chart_type}_{timestamp}.png'
        filepath = charts_dir / filename
        plt.savefig(filepath, dpi=150, bbox_inches='tight')
        plt.close()
        
        return {
            "chart_type": chart_type,
            "file_path": str(filepath.relative_to(_PROJECT_ROOT)),
            "absolute_path": str(filepath),
        }
    else:
        # Return as base64
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
        plt.close()
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        return {
            "chart_type": chart_type,
            "format": "png",
            "encoding": "base64",
            "image_data": image_base64,
            "display_note": "Use this base64 string to display the image",
        }


@mcp.tool()
def merge_datasets(
    file_path_left: str,
    file_path_right: str,
    on: list[str] | None = None,
    left_on: str | None = None,
    right_on: str | None = None,
    how: str = "inner",
    preview_limit: int = 50,
) -> dict[str, Any]:
    """
    Merge/join two datasets together - essential for combining data sources.
    
    Args:
        file_path_left: Path to left/primary dataset
        file_path_right: Path to right/secondary dataset
        on: Column(s) to join on (if same name in both datasets)
        left_on: Column name in left dataset to join on
        right_on: Column name in right dataset to join on
        how: Join type - 'inner', 'left', 'right', 'outer'
        preview_limit: Number of rows to return in preview
    
    Returns:
        Dictionary containing merged data preview and statistics
    """
    df_left = _load_data(file_path_left)
    df_right = _load_data(file_path_right)
    
    valid_how = ['inner', 'left', 'right', 'outer']
    if how not in valid_how:
        raise ValueError(f"Unknown join type: {how}. Use: {valid_how}")
    
    # Determine join keys
    if on:
        invalid_left = [c for c in on if c not in df_left.columns]
        invalid_right = [c for c in on if c not in df_right.columns]
        if invalid_left:
            raise ValueError(f"Columns {invalid_left} not found in left dataset")
        if invalid_right:
            raise ValueError(f"Columns {invalid_right} not found in right dataset")
        merged = pd.merge(df_left, df_right, on=on, how=how)
    elif left_on and right_on:
        if left_on not in df_left.columns:
            raise ValueError(f"Column '{left_on}' not found in left dataset")
        if right_on not in df_right.columns:
            raise ValueError(f"Column '{right_on}' not found in right dataset")
        merged = pd.merge(df_left, df_right, left_on=left_on, right_on=right_on, how=how)
    else:
        # Try to find common columns
        common_cols = list(set(df_left.columns) & set(df_right.columns))
        if not common_cols:
            raise ValueError("No common columns found. Specify 'on', or 'left_on' and 'right_on'")
        on = common_cols[:1]  # Use first common column
        merged = pd.merge(df_left, df_right, on=on, how=how)
    
    # Statistics about the merge
    left_rows = len(df_left)
    right_rows = len(df_right)
    merged_rows = len(merged)
    
    merge_stats = {
        "left_rows": left_rows,
        "right_rows": right_rows,
        "merged_rows": merged_rows,
        "join_type": how,
        "join_keys": on if on else {"left": left_on, "right": right_on},
    }
    
    if how == "inner":
        merge_stats["left_match_pct"] = round(merged_rows / left_rows * 100, 1) if left_rows > 0 else 0
        merge_stats["right_match_pct"] = round(merged_rows / right_rows * 100, 1) if right_rows > 0 else 0
    
    return {
        "merge_stats": merge_stats,
        "merged_columns": merged.columns.tolist(),
        "merged_shape": {"rows": merged_rows, "columns": len(merged.columns)},
        "preview": merged.head(preview_limit).to_dict(orient="records"),
        "has_more": merged_rows > preview_limit,
    }


@mcp.tool()
def statistical_test(
    file_path: str,
    test_type: str,
    column1: str,
    column2: str | None = None,
    group_column: str | None = None,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """
    Perform statistical hypothesis tests on data.
    
    Args:
        file_path: Path to CSV or SQLite file
        test_type: Type of test:
            - 'ttest_ind': Independent samples t-test (compare 2 groups)
            - 'ttest_paired': Paired samples t-test
            - 'chi_squared': Chi-squared test for categorical independence
            - 'anova': One-way ANOVA (compare 3+ groups)
            - 'mann_whitney': Non-parametric alternative to t-test
            - 'pearson': Pearson correlation test
            - 'spearman': Spearman correlation test
        column1: First column for analysis
        column2: Second column (required for correlation, optional for t-test)
        group_column: Column defining groups (for t-test, ANOVA)
        alpha: Significance level (default 0.05)
    
    Returns:
        Dictionary containing test statistic, p-value, and interpretation
    """
    df = _load_data(file_path)
    
    if column1 not in df.columns:
        raise ValueError(f"Column '{column1}' not found")
    
    result = {
        "test_type": test_type,
        "alpha": alpha,
        "columns_tested": [column1],
    }
    
    if test_type == "ttest_ind":
        # Independent samples t-test
        if group_column is None:
            raise ValueError("group_column is required for independent t-test")
        if group_column not in df.columns:
            raise ValueError(f"Group column '{group_column}' not found")
        
        groups = df[group_column].unique()
        if len(groups) != 2:
            raise ValueError(f"t-test requires exactly 2 groups, found {len(groups)}: {groups.tolist()}")
        
        group1_data = df[df[group_column] == groups[0]][column1].dropna()
        group2_data = df[df[group_column] == groups[1]][column1].dropna()
        
        t_stat, p_value = stats.ttest_ind(group1_data, group2_data)
        
        result.update({
            "groups": groups.tolist(),
            "group_means": {str(groups[0]): float(group1_data.mean()), str(groups[1]): float(group2_data.mean())},
            "group_sizes": {str(groups[0]): len(group1_data), str(groups[1]): len(group2_data)},
            "t_statistic": float(t_stat),
            "p_value": float(p_value),
            "significant": p_value < alpha,
            "interpretation": f"The difference between groups is {'statistically significant' if p_value < alpha else 'not statistically significant'} at α={alpha}",
        })
        
    elif test_type == "ttest_paired":
        if column2 is None:
            raise ValueError("column2 is required for paired t-test")
        if column2 not in df.columns:
            raise ValueError(f"Column '{column2}' not found")
        
        data1 = df[column1].dropna()
        data2 = df[column2].dropna()
        
        # Align data
        mask = df[column1].notna() & df[column2].notna()
        data1 = df.loc[mask, column1]
        data2 = df.loc[mask, column2]
        
        t_stat, p_value = stats.ttest_rel(data1, data2)
        
        result.update({
            "columns_tested": [column1, column2],
            "means": {column1: float(data1.mean()), column2: float(data2.mean())},
            "sample_size": len(data1),
            "mean_difference": float(data1.mean() - data2.mean()),
            "t_statistic": float(t_stat),
            "p_value": float(p_value),
            "significant": p_value < alpha,
            "interpretation": f"The paired difference is {'statistically significant' if p_value < alpha else 'not statistically significant'} at α={alpha}",
        })
        
    elif test_type == "chi_squared":
        if column2 is None:
            raise ValueError("column2 is required for chi-squared test")
        if column2 not in df.columns:
            raise ValueError(f"Column '{column2}' not found")
        
        contingency_table = pd.crosstab(df[column1], df[column2])
        chi2, p_value, dof, expected = stats.chi2_contingency(contingency_table)
        
        result.update({
            "columns_tested": [column1, column2],
            "chi2_statistic": float(chi2),
            "degrees_of_freedom": int(dof),
            "p_value": float(p_value),
            "significant": p_value < alpha,
            "interpretation": f"The variables are {'dependent (associated)' if p_value < alpha else 'independent'} at α={alpha}",
            "contingency_table_shape": contingency_table.shape,
        })
        
    elif test_type == "anova":
        if group_column is None:
            raise ValueError("group_column is required for ANOVA")
        if group_column not in df.columns:
            raise ValueError(f"Group column '{group_column}' not found")
        
        groups = df[group_column].unique()
        if len(groups) < 3:
            raise ValueError(f"ANOVA requires 3+ groups, found {len(groups)}. Use t-test for 2 groups.")
        
        group_data = [df[df[group_column] == g][column1].dropna() for g in groups]
        f_stat, p_value = stats.f_oneway(*group_data)
        
        group_means = {str(g): float(df[df[group_column] == g][column1].mean()) for g in groups}
        
        result.update({
            "groups": groups.tolist(),
            "group_means": group_means,
            "group_sizes": {str(g): len(df[df[group_column] == g]) for g in groups},
            "f_statistic": float(f_stat),
            "p_value": float(p_value),
            "significant": p_value < alpha,
            "interpretation": f"At least one group mean is {'significantly different' if p_value < alpha else 'not significantly different'} at α={alpha}",
        })
        
    elif test_type == "mann_whitney":
        if group_column is None:
            raise ValueError("group_column is required for Mann-Whitney test")
        
        groups = df[group_column].unique()
        if len(groups) != 2:
            raise ValueError(f"Mann-Whitney requires exactly 2 groups, found {len(groups)}")
        
        group1_data = df[df[group_column] == groups[0]][column1].dropna()
        group2_data = df[df[group_column] == groups[1]][column1].dropna()
        
        u_stat, p_value = stats.mannwhitneyu(group1_data, group2_data, alternative='two-sided')
        
        result.update({
            "groups": groups.tolist(),
            "group_medians": {str(groups[0]): float(group1_data.median()), str(groups[1]): float(group2_data.median())},
            "u_statistic": float(u_stat),
            "p_value": float(p_value),
            "significant": p_value < alpha,
            "interpretation": f"The distributions are {'significantly different' if p_value < alpha else 'not significantly different'} at α={alpha}",
        })
        
    elif test_type in ["pearson", "spearman"]:
        if column2 is None:
            raise ValueError(f"column2 is required for {test_type} correlation")
        if column2 not in df.columns:
            raise ValueError(f"Column '{column2}' not found")
        
        mask = df[column1].notna() & df[column2].notna()
        data1 = df.loc[mask, column1]
        data2 = df.loc[mask, column2]
        
        if test_type == "pearson":
            corr, p_value = stats.pearsonr(data1, data2)
        else:
            corr, p_value = stats.spearmanr(data1, data2)
        
        result.update({
            "columns_tested": [column1, column2],
            "correlation": float(corr),
            "strength": _interpret_correlation(abs(corr)),
            "direction": "positive" if corr > 0 else "negative" if corr < 0 else "none",
            "p_value": float(p_value),
            "significant": p_value < alpha,
            "sample_size": len(data1),
            "interpretation": f"There is a {_interpret_correlation(abs(corr))} {'positive' if corr > 0 else 'negative'} correlation that is {'statistically significant' if p_value < alpha else 'not statistically significant'} at α={alpha}",
        })
        
    else:
        valid_tests = ['ttest_ind', 'ttest_paired', 'chi_squared', 'anova', 'mann_whitney', 'pearson', 'spearman']
        raise ValueError(f"Unknown test_type: {test_type}. Use: {valid_tests}")
    
    return result


@mcp.tool()
def auto_insights(file_path: str, max_insights: int = 10) -> dict[str, Any]:
    """
    Automatically generate interesting insights about a dataset.
    Perfect for quick data exploration and understanding.
    
    Args:
        file_path: Path to CSV or SQLite file
        max_insights: Maximum number of insights to generate (default 10)
    
    Returns:
        Dictionary containing automatically discovered insights
    """
    df = _load_data(file_path)
    insights = []
    
    numeric_cols = _get_numeric_columns(df)
    cat_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
    
    # 1. Dataset overview
    insights.append({
        "category": "overview",
        "title": "Dataset Size",
        "insight": f"The dataset contains {len(df):,} rows and {len(df.columns)} columns ({len(numeric_cols)} numeric, {len(cat_cols)} categorical).",
        "importance": "high",
    })
    
    # 2. Missing data insights
    missing_total = df.isnull().sum().sum()
    if missing_total > 0:
        most_missing_col = df.isnull().sum().idxmax()
        most_missing_pct = df[most_missing_col].isnull().mean() * 100
        insights.append({
            "category": "data_quality",
            "title": "Missing Values Alert",
            "insight": f"Found {missing_total:,} missing values total. Column '{most_missing_col}' has the most missing data ({most_missing_pct:.1f}%).",
            "importance": "high" if most_missing_pct > 20 else "medium",
        })
    
    # 3. Numeric column insights
    for col in numeric_cols[:5]:  # Limit to first 5
        col_data = df[col].dropna()
        if len(col_data) == 0:
            continue
            
        # Skewness insight
        skew = col_data.skew()
        if abs(skew) > 1:
            direction = "right (positive)" if skew > 0 else "left (negative)"
            insights.append({
                "category": "distribution",
                "title": f"Skewed Distribution: {col}",
                "insight": f"'{col}' is highly skewed to the {direction} (skewness: {skew:.2f}). Consider log transformation for analysis.",
                "importance": "medium",
            })
        
        # Outlier insight
        q1, q3 = col_data.quantile([0.25, 0.75])
        iqr = q3 - q1
        outliers = ((col_data < q1 - 1.5 * iqr) | (col_data > q3 + 1.5 * iqr)).sum()
        if outliers > 0:
            outlier_pct = outliers / len(col_data) * 100
            if outlier_pct > 5:
                insights.append({
                    "category": "outliers",
                    "title": f"Outliers Detected: {col}",
                    "insight": f"'{col}' has {outliers} outliers ({outlier_pct:.1f}% of data). Range: {col_data.min():.2f} to {col_data.max():.2f}.",
                    "importance": "medium",
                })
    
    # 4. Top correlations
    if len(numeric_cols) >= 2:
        corr_matrix = df[numeric_cols].corr()
        for i, col1 in enumerate(corr_matrix.columns):
            for j, col2 in enumerate(corr_matrix.columns):
                if i < j:
                    corr_val = corr_matrix.loc[col1, col2]
                    if abs(corr_val) > 0.7 and not np.isnan(corr_val):
                        direction = "positive" if corr_val > 0 else "negative"
                        insights.append({
                            "category": "correlation",
                            "title": f"Strong Correlation Found",
                            "insight": f"'{col1}' and '{col2}' have a strong {direction} correlation ({corr_val:.2f}).",
                            "importance": "high",
                        })
    
    # 5. Categorical column insights
    for col in cat_cols[:3]:  # Limit to first 3
        unique_count = df[col].nunique()
        value_counts = df[col].value_counts()
        
        if unique_count <= 1:
            insights.append({
                "category": "data_quality",
                "title": f"Constant Column: {col}",
                "insight": f"'{col}' has only {unique_count} unique value(s). Consider removing.",
                "importance": "medium",
            })
        elif unique_count == len(df):
            insights.append({
                "category": "data_structure",
                "title": f"Unique Identifier: {col}",
                "insight": f"'{col}' has all unique values - likely a primary key/identifier.",
                "importance": "low",
            })
        else:
            top_value = value_counts.index[0]
            top_pct = value_counts.iloc[0] / len(df) * 100
            if top_pct > 50:
                insights.append({
                    "category": "distribution",
                    "title": f"Dominant Category: {col}",
                    "insight": f"'{col}' is dominated by '{top_value}' ({top_pct:.1f}% of data).",
                    "importance": "medium",
                })
    
    # 6. Date column detection
    for col in df.columns:
        if df[col].dtype == 'object':
            try:
                parsed = pd.to_datetime(df[col], errors='coerce')
                if parsed.notna().sum() > len(df) * 0.5:  # More than 50% valid dates
                    date_range = parsed.dropna()
                    insights.append({
                        "category": "temporal",
                        "title": f"Date Column Detected: {col}",
                        "insight": f"'{col}' contains dates from {date_range.min().date()} to {date_range.max().date()} ({(date_range.max() - date_range.min()).days} days span).",
                        "importance": "medium",
                    })
                    break  # Only report first date column
            except:
                pass
    
    # 7. Summary statistics insight
    if numeric_cols:
        main_col = numeric_cols[0]
        main_data = df[main_col].dropna()
        if len(main_data) > 0:
            insights.append({
                "category": "statistics",
                "title": f"Key Metric Summary: {main_col}",
                "insight": f"'{main_col}' ranges from {main_data.min():,.2f} to {main_data.max():,.2f} with mean {main_data.mean():,.2f} and median {main_data.median():,.2f}.",
                "importance": "medium",
            })
    
    # Sort by importance and limit
    importance_order = {"high": 0, "medium": 1, "low": 2}
    insights.sort(key=lambda x: importance_order.get(x["importance"], 2))
    insights = insights[:max_insights]
    
    return {
        "file": file_path,
        "total_insights": len(insights),
        "insights": insights,
        "recommendation": "Use describe_dataset() for detailed statistics, or specific tools like detect_anomalies() to investigate further.",
    }


@mcp.tool()
def export_data(
    file_path: str,
    output_name: str,
    filter_column: str | None = None,
    filter_operator: str | None = None,
    filter_value: str | float | None = None,
    columns: list[str] | None = None,
    sort_by: str | None = None,
    sort_ascending: bool = True,
    limit: int | None = None,
) -> dict[str, Any]:
    """
    Export filtered/transformed data to a new CSV file.
    
    Args:
        file_path: Path to source CSV or SQLite file
        output_name: Name for output file (without extension, saved to data/ folder)
        filter_column: Optional column to filter on
        filter_operator: Filter operator - 'eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'contains'
        filter_value: Value to filter by
        columns: List of columns to include (default: all)
        sort_by: Column to sort by
        sort_ascending: Sort direction (default: ascending)
        limit: Maximum rows to export
    
    Returns:
        Dictionary containing export details and file path
    """
    df = _load_data(file_path)
    original_count = len(df)
    
    # Apply filter if specified
    if filter_column and filter_operator and filter_value is not None:
        if filter_column not in df.columns:
            raise ValueError(f"Filter column '{filter_column}' not found")
        
        if filter_operator == "eq":
            df = df[df[filter_column] == filter_value]
        elif filter_operator == "ne":
            df = df[df[filter_column] != filter_value]
        elif filter_operator == "gt":
            df = df[df[filter_column] > float(filter_value)]
        elif filter_operator == "gte":
            df = df[df[filter_column] >= float(filter_value)]
        elif filter_operator == "lt":
            df = df[df[filter_column] < float(filter_value)]
        elif filter_operator == "lte":
            df = df[df[filter_column] <= float(filter_value)]
        elif filter_operator == "contains":
            df = df[df[filter_column].astype(str).str.contains(str(filter_value), case=False, na=False)]
        else:
            raise ValueError(f"Unknown operator: {filter_operator}")
    
    # Select columns
    if columns:
        invalid = [c for c in columns if c not in df.columns]
        if invalid:
            raise ValueError(f"Columns not found: {invalid}")
        df = df[columns]
    
    # Sort
    if sort_by:
        if sort_by not in df.columns:
            raise ValueError(f"Sort column '{sort_by}' not found")
        df = df.sort_values(sort_by, ascending=sort_ascending)
    
    # Limit rows
    if limit:
        df = df.head(limit)
    
    # Save file
    output_dir = _PROJECT_ROOT / 'data'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Clean output name and add timestamp
    clean_name = "".join(c for c in output_name if c.isalnum() or c in ('-', '_'))
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = output_dir / f"{clean_name}_{timestamp}.csv"
    
    df.to_csv(output_file, index=False)
    
    return {
        "success": True,
        "source_file": file_path,
        "output_file": str(output_file.relative_to(_PROJECT_ROOT)),
        "absolute_path": str(output_file),
        "original_rows": original_count,
        "exported_rows": len(df),
        "exported_columns": df.columns.tolist(),
        "filter_applied": f"{filter_column} {filter_operator} {filter_value}" if filter_column else None,
    }


def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
