# MCP Tabular Data Analysis Server
A Model Context Protocol (MCP) server that provides tools for analyzing numeric and tabular data. Works with CSV files and SQLite databases.

## Features


### Core Tools

| Tool | Description |
| :--- | :--- |
| **`list_data_files`** | List available CSV and SQLite files in the data directory |
| **`describe_dataset`** | Generate statistics for a dataset (shape, types, distributions, missing values) |
| **`detect_anomalies`** | Find outliers using Z-score or IQR methods |
| **`compute_correlation`** | Calculate correlation matrices between numeric columns |
| **`filter_rows`** | Filter data using various operators (eq, gt, lt, contains, etc.) |
| **`group_aggregate`** | Group data and compute aggregations (sum, mean, count, etc.) |
| **`query_sqlite`** | Execute SQL queries on SQLite databases |
| **`list_tables`** | List all tables and schemas in a SQLite database |

### Analytics Tools

| Tool | Description |
| :--- | :--- |
| **`create_pivot_table`** | Create Excel-style pivot tables with flexible aggregations |
| **`data_quality_report`** | Data quality assessment with scores and recommendations |
| **`analyze_time_series`** | Time series analysis with trends, seasonality, and moving averages |
| **`generate_chart`** | Create visualizations (bar, line, scatter, histogram, pie, box plots) |
| **`merge_datasets`** | Join/merge two datasets together (inner, left, right, outer joins) |
| **`statistical_test`** | Hypothesis testing (t-test, ANOVA, chi-squared, correlation tests) |
| **`auto_insights`** | Discover patterns and insights |
| **`export_data`** | Export filtered/transformed data to new CSV files |
