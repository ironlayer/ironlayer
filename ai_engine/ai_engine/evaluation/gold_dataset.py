"""Curated gold dataset for AI engine evaluation and regression testing.

Contains 50+ entries of realistic Databricks SQL pairs (old/new) with
expected classification outcomes.  The dataset is code -- not a data file --
so it is version-controlled and reviewed alongside engine changes.

Each entry's ``expected_change_type`` is aligned with the rule-based
classifier's logic so that deterministic regression assertions pass
without any LLM involvement.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class GoldDatasetEntry(BaseModel):
    """A single evaluation entry in the gold dataset."""

    id: str = Field(..., description="Unique identifier for this entry.")
    category: str = Field(..., description="Category grouping for analysis.")
    old_sql: str = Field(..., description="SQL before the change (empty for new models).")
    new_sql: str = Field(..., description="SQL after the change.")
    schema_diff: dict | None = Field(default=None, description="Optional column-level diff.")
    expected_change_type: str = Field(..., description="Expected classification from the rule-based classifier.")
    expected_confidence_min: float = Field(default=0.0, ge=0.0, le=1.0, description="Minimum expected confidence.")
    expected_confidence_max: float = Field(default=1.0, ge=0.0, le=1.0, description="Maximum expected confidence.")
    expected_full_rebuild: bool = Field(default=False, description="Whether the change requires a full rebuild.")
    expected_risk_factors: list[str] = Field(
        default_factory=list,
        description="Expected risk factor keywords (for risk scorer evaluation).",
    )
    expected_suggestion_types: list[str] = Field(
        default_factory=list,
        description="Expected optimizer suggestion types.",
    )


class GoldDataset:
    """Curated collection of evaluation entries for AI engines.

    The dataset is organised into categories that cover the full range of
    change types the classifier must handle.
    """

    ENTRIES: list[GoldDatasetEntry] = [
        # =================================================================
        # COSMETIC (5 entries) -- whitespace, comments, formatting only
        # =================================================================
        GoldDatasetEntry(
            id="cosmetic_001",
            category="cosmetic",
            old_sql=(
                "SELECT order_id, customer_id, order_date, total_amount "
                "FROM catalog.schema.orders WHERE status = 'completed'"
            ),
            new_sql=(
                "SELECT  order_id,  customer_id,  order_date,  total_amount "
                "FROM  catalog.schema.orders  WHERE  status = 'completed'"
            ),
            expected_change_type="cosmetic",
            expected_confidence_min=0.9,
            expected_full_rebuild=False,
        ),
        GoldDatasetEntry(
            id="cosmetic_002",
            category="cosmetic",
            old_sql=("SELECT id, name, created_at FROM catalog.schema.users"),
            new_sql=("-- Updated formatting 2024-01\n" "SELECT id, name, created_at FROM catalog.schema.users"),
            expected_change_type="cosmetic",
            expected_confidence_min=0.9,
            expected_full_rebuild=False,
        ),
        GoldDatasetEntry(
            id="cosmetic_003",
            category="cosmetic",
            old_sql=(
                "SELECT a.id,a.name,b.total FROM catalog.schema.users a "
                "JOIN catalog.schema.orders b ON a.id=b.user_id"
            ),
            new_sql=(
                "SELECT a.id, a.name, b.total FROM catalog.schema.users a "
                "JOIN catalog.schema.orders b ON a.id = b.user_id"
            ),
            expected_change_type="cosmetic",
            expected_confidence_min=0.9,
            expected_full_rebuild=False,
        ),
        GoldDatasetEntry(
            id="cosmetic_004",
            category="cosmetic",
            old_sql=("select order_id, total from catalog.schema.orders"),
            new_sql=("SELECT order_id, total FROM catalog.schema.orders"),
            expected_change_type="cosmetic",
            expected_confidence_min=0.9,
            expected_full_rebuild=False,
        ),
        GoldDatasetEntry(
            id="cosmetic_005",
            category="cosmetic",
            old_sql=("SELECT id, /* primary key */ name FROM catalog.schema.users"),
            new_sql=("SELECT id, /* user primary key */ name FROM catalog.schema.users"),
            expected_change_type="cosmetic",
            expected_confidence_min=0.9,
            expected_full_rebuild=False,
        ),
        # =================================================================
        # BREAKING (10 entries) -- column removals, type changes, etc.
        # =================================================================
        GoldDatasetEntry(
            id="breaking_001",
            category="breaking",
            old_sql=(
                "SELECT order_id, customer_id, order_date, total_amount, discount "
                "FROM catalog.schema.orders WHERE status = 'completed'"
            ),
            new_sql=(
                "SELECT order_id, customer_id, order_date, total_amount "
                "FROM catalog.schema.orders WHERE status = 'completed'"
            ),
            schema_diff={"removed": ["discount"]},
            expected_change_type="breaking",
            expected_confidence_min=0.8,
            expected_full_rebuild=True,
            expected_risk_factors=["column_removed"],
        ),
        GoldDatasetEntry(
            id="breaking_002",
            category="breaking",
            old_sql=(
                "SELECT o.order_id, o.total_amount, c.name "
                "FROM catalog.schema.orders o "
                "JOIN catalog.schema.customers c ON o.customer_id = c.id"
            ),
            new_sql=(
                "SELECT o.order_id, o.total_amount, c.name "
                "FROM catalog.schema.orders o "
                "LEFT JOIN catalog.schema.customers c ON o.customer_id = c.id"
            ),
            expected_change_type="breaking",
            expected_confidence_min=0.7,
            expected_full_rebuild=True,
            expected_risk_factors=["join_type_changed"],
        ),
        GoldDatasetEntry(
            id="breaking_003",
            category="breaking",
            old_sql=(
                "SELECT order_id, customer_id, total_amount " "FROM catalog.schema.orders WHERE status = 'completed'"
            ),
            new_sql=("SELECT order_id, customer_id, total_amount " "FROM catalog.schema.orders"),
            expected_change_type="breaking",
            expected_confidence_min=0.7,
            expected_full_rebuild=True,
            expected_risk_factors=["filter_removed"],
        ),
        GoldDatasetEntry(
            id="breaking_004",
            category="breaking",
            old_sql=(
                "WITH daily AS (\n"
                "  SELECT date_trunc('day', created_at) AS day, COUNT(*) AS cnt\n"
                "  FROM catalog.schema.events GROUP BY 1\n"
                ")\n"
                "SELECT day, cnt FROM daily"
            ),
            new_sql=(
                "WITH daily AS (\n"
                "  SELECT date_trunc('day', created_at) AS day, COUNT(*) AS cnt\n"
                "  FROM catalog.schema.events GROUP BY 1\n"
                ")\n"
                "SELECT day FROM daily"
            ),
            schema_diff={"removed": ["cnt"]},
            expected_change_type="breaking",
            expected_confidence_min=0.8,
            expected_full_rebuild=True,
        ),
        GoldDatasetEntry(
            id="breaking_005",
            category="breaking",
            old_sql=(
                "SELECT user_id, email, CAST(balance AS DECIMAL(10,2)) AS balance " "FROM catalog.schema.accounts"
            ),
            new_sql=("SELECT user_id, email, CAST(balance AS INT) AS balance " "FROM catalog.schema.accounts"),
            schema_diff={"modified": [{"column": "balance", "old_type": "DECIMAL", "new_type": "INT"}]},
            expected_change_type="breaking",
            expected_confidence_min=0.8,
            expected_full_rebuild=True,
        ),
        GoldDatasetEntry(
            id="breaking_006",
            category="breaking",
            old_sql=("SELECT id, name, region FROM catalog.schema.stores " "WHERE region IN ('US', 'EU', 'APAC')"),
            new_sql=("SELECT id, name FROM catalog.schema.stores " "WHERE region IN ('US', 'EU', 'APAC')"),
            schema_diff={"removed": ["region"]},
            expected_change_type="breaking",
            expected_confidence_min=0.8,
            expected_full_rebuild=True,
        ),
        GoldDatasetEntry(
            id="breaking_007",
            category="breaking",
            old_sql=(
                "SELECT p.product_id, p.name, c.category_name "
                "FROM catalog.schema.products p "
                "INNER JOIN catalog.schema.categories c ON p.category_id = c.id "
                "WHERE p.active = true"
            ),
            new_sql=("SELECT p.product_id, p.name " "FROM catalog.schema.products p " "WHERE p.active = true"),
            schema_diff={"removed": ["category_name"]},
            expected_change_type="breaking",
            expected_confidence_min=0.8,
            expected_full_rebuild=True,
        ),
        GoldDatasetEntry(
            id="breaking_008",
            category="breaking",
            old_sql=(
                "SELECT order_id, customer_id, order_date "
                "FROM catalog.schema.orders "
                "WHERE order_date >= '2024-01-01'"
            ),
            new_sql=("SELECT order_id, order_date " "FROM catalog.schema.orders " "WHERE order_date >= '2024-01-01'"),
            schema_diff={"removed": ["customer_id"]},
            expected_change_type="breaking",
            expected_confidence_min=0.8,
            expected_full_rebuild=True,
        ),
        GoldDatasetEntry(
            id="breaking_009",
            category="breaking",
            old_sql=("SELECT id, ts, value FROM catalog.schema.metrics " "WHERE ts >= CURRENT_DATE - INTERVAL 30 DAY"),
            new_sql=(
                "SELECT id, ts, value, quality_flag FROM catalog.schema.metrics_v2 "
                "WHERE ts >= CURRENT_DATE - INTERVAL 30 DAY"
            ),
            expected_change_type="breaking",
            expected_confidence_min=0.7,
            expected_full_rebuild=True,
        ),
        GoldDatasetEntry(
            id="breaking_010",
            category="breaking",
            old_sql=(
                "SELECT t.id, t.amount, t.currency, e.rate "
                "FROM catalog.schema.transactions t "
                "JOIN catalog.schema.exchange_rates e "
                "ON t.currency = e.currency AND t.txn_date = e.rate_date"
            ),
            new_sql=(
                "SELECT t.id, t.amount, t.currency, e.rate "
                "FROM catalog.schema.transactions t "
                "JOIN catalog.schema.exchange_rates e "
                "ON t.currency = e.currency"
            ),
            expected_change_type="breaking",
            expected_confidence_min=0.7,
            expected_full_rebuild=True,
        ),
        # =================================================================
        # NON-BREAKING (8 entries) -- safe additions and narrowing
        # =================================================================
        GoldDatasetEntry(
            id="non_breaking_001",
            category="non_breaking",
            old_sql=("SELECT order_id, customer_id, total_amount " "FROM catalog.schema.orders"),
            new_sql=("SELECT order_id, customer_id, total_amount, created_at " "FROM catalog.schema.orders"),
            schema_diff={"added": ["created_at"]},
            expected_change_type="non_breaking",
            expected_confidence_min=0.7,
            expected_full_rebuild=False,
        ),
        GoldDatasetEntry(
            id="non_breaking_002",
            category="non_breaking",
            old_sql=("SELECT id, name, email FROM catalog.schema.users"),
            new_sql=("SELECT id, name, email FROM catalog.schema.users " "WHERE active = true"),
            expected_change_type="non_breaking",
            expected_confidence_min=0.7,
            expected_full_rebuild=False,
        ),
        GoldDatasetEntry(
            id="non_breaking_003",
            category="non_breaking",
            old_sql=("SELECT product_id, name, price FROM catalog.schema.products"),
            new_sql=("SELECT product_id, name, price FROM catalog.schema.products " "ORDER BY name ASC"),
            expected_change_type="non_breaking",
            expected_confidence_min=0.7,
            expected_full_rebuild=False,
        ),
        GoldDatasetEntry(
            id="non_breaking_004",
            category="non_breaking",
            old_sql=("SELECT id, amount FROM catalog.schema.payments"),
            new_sql=(
                "WITH valid_payments AS (\n"
                "  SELECT id, amount FROM catalog.schema.payments "
                "WHERE amount > 0\n"
                ")\n"
                "SELECT id, amount FROM valid_payments"
            ),
            expected_change_type="non_breaking",
            expected_confidence_min=0.6,
            expected_full_rebuild=False,
        ),
        GoldDatasetEntry(
            id="non_breaking_005",
            category="non_breaking",
            old_sql=("SELECT id, name, email FROM catalog.schema.users"),
            new_sql=("SELECT id, name, email, phone FROM catalog.schema.users"),
            schema_diff={"added": ["phone"]},
            expected_change_type="non_breaking",
            expected_confidence_min=0.7,
            expected_full_rebuild=False,
        ),
        GoldDatasetEntry(
            id="non_breaking_006",
            category="non_breaking",
            old_sql=("SELECT order_id, total FROM catalog.schema.orders"),
            new_sql=("SELECT order_id, total FROM catalog.schema.orders " "WHERE total > 0"),
            expected_change_type="non_breaking",
            expected_confidence_min=0.7,
            expected_full_rebuild=False,
        ),
        GoldDatasetEntry(
            id="non_breaking_007",
            category="non_breaking",
            old_sql=("SELECT id, ts, value FROM catalog.schema.metrics"),
            new_sql=(
                "SELECT id, ts, value, " "LAG(value) OVER (ORDER BY ts) AS prev_value " "FROM catalog.schema.metrics"
            ),
            schema_diff={"added": ["prev_value"]},
            expected_change_type="non_breaking",
            expected_confidence_min=0.6,
            expected_full_rebuild=False,
        ),
        GoldDatasetEntry(
            id="non_breaking_008",
            category="non_breaking",
            old_sql=("SELECT id, category, amount FROM catalog.schema.expenses"),
            new_sql=("SELECT id, category, amount, CURRENT_TIMESTAMP AS etl_loaded_at " "FROM catalog.schema.expenses"),
            schema_diff={"added": ["etl_loaded_at"]},
            expected_change_type="non_breaking",
            expected_confidence_min=0.7,
            expected_full_rebuild=False,
        ),
        # =================================================================
        # RENAME_ONLY (5 entries) -- alias changes only
        # =================================================================
        GoldDatasetEntry(
            id="rename_001",
            category="rename_only",
            old_sql=("SELECT order_id AS oid, customer_id AS cid " "FROM catalog.schema.orders"),
            new_sql=(
                "SELECT order_id AS order_identifier, customer_id AS customer_identifier " "FROM catalog.schema.orders"
            ),
            expected_change_type="rename_only",
            expected_confidence_min=0.7,
            expected_full_rebuild=False,
        ),
        GoldDatasetEntry(
            id="rename_002",
            category="rename_only",
            old_sql=("WITH cte AS (SELECT id, name FROM catalog.schema.users) " "SELECT id, name FROM cte"),
            new_sql=("WITH user_data AS (SELECT id, name FROM catalog.schema.users) " "SELECT id, name FROM user_data"),
            expected_change_type="rename_only",
            expected_confidence_min=0.7,
            expected_full_rebuild=False,
        ),
        GoldDatasetEntry(
            id="rename_003",
            category="rename_only",
            old_sql=("SELECT a.id, a.name FROM catalog.schema.users a"),
            new_sql=("SELECT u.id, u.name FROM catalog.schema.users u"),
            expected_change_type="rename_only",
            expected_confidence_min=0.7,
            expected_full_rebuild=False,
        ),
        GoldDatasetEntry(
            id="rename_004",
            category="rename_only",
            old_sql=("SELECT t.id AS txn_id, t.amt AS txn_amount " "FROM catalog.schema.transactions t"),
            new_sql=(
                "SELECT t.id AS transaction_id, t.amt AS transaction_amount " "FROM catalog.schema.transactions t"
            ),
            expected_change_type="rename_only",
            expected_confidence_min=0.7,
            expected_full_rebuild=False,
        ),
        GoldDatasetEntry(
            id="rename_005",
            category="rename_only",
            old_sql=(
                "SELECT o.id, o.total FROM catalog.schema.orders o "
                "JOIN catalog.schema.customers c ON o.cust_id = c.id"
            ),
            new_sql=(
                "SELECT orders.id, orders.total FROM catalog.schema.orders orders "
                "JOIN catalog.schema.customers customers ON orders.cust_id = customers.id"
            ),
            expected_change_type="rename_only",
            expected_confidence_min=0.7,
            expected_full_rebuild=False,
        ),
        # =================================================================
        # METRIC_SEMANTIC (8 entries) -- aggregate/metric logic changes
        # =================================================================
        GoldDatasetEntry(
            id="metric_001",
            category="metric_semantic",
            old_sql=(
                "SELECT customer_id, SUM(total_amount) AS revenue " "FROM catalog.schema.orders GROUP BY customer_id"
            ),
            new_sql=(
                "SELECT customer_id, AVG(total_amount) AS revenue " "FROM catalog.schema.orders GROUP BY customer_id"
            ),
            expected_change_type="metric_semantic",
            expected_confidence_min=0.8,
            expected_full_rebuild=True,
        ),
        GoldDatasetEntry(
            id="metric_002",
            category="metric_semantic",
            old_sql=("SELECT region, COUNT(*) AS order_count " "FROM catalog.schema.orders GROUP BY region"),
            new_sql=(
                "SELECT region, COUNT(DISTINCT customer_id) AS order_count "
                "FROM catalog.schema.orders GROUP BY region"
            ),
            expected_change_type="metric_semantic",
            expected_confidence_min=0.8,
            expected_full_rebuild=True,
        ),
        GoldDatasetEntry(
            id="metric_003",
            category="metric_semantic",
            old_sql=(
                "SELECT product_id, SUM(quantity) AS total_qty " "FROM catalog.schema.order_items GROUP BY product_id"
            ),
            new_sql=(
                "SELECT product_id, SUM(quantity) AS total_qty "
                "FROM catalog.schema.order_items GROUP BY product_id "
                "HAVING SUM(quantity) > 100"
            ),
            expected_change_type="metric_semantic",
            expected_confidence_min=0.7,
            expected_full_rebuild=True,
        ),
        GoldDatasetEntry(
            id="metric_004",
            category="metric_semantic",
            old_sql=(
                "SELECT date_trunc('day', ts) AS day, SUM(amount) AS daily_total "
                "FROM catalog.schema.transactions GROUP BY 1"
            ),
            new_sql=(
                "SELECT date_trunc('week', ts) AS week, SUM(amount) AS weekly_total "
                "FROM catalog.schema.transactions GROUP BY 1"
            ),
            expected_change_type="metric_semantic",
            expected_confidence_min=0.8,
            expected_full_rebuild=True,
        ),
        GoldDatasetEntry(
            id="metric_005",
            category="metric_semantic",
            old_sql=(
                "SELECT user_id, "
                "  SUM(amount) OVER (PARTITION BY user_id ORDER BY ts "
                "    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_total "
                "FROM catalog.schema.payments"
            ),
            new_sql=(
                "SELECT user_id, "
                "  SUM(amount) OVER (PARTITION BY user_id ORDER BY ts "
                "    ROWS BETWEEN 30 PRECEDING AND CURRENT ROW) AS running_total "
                "FROM catalog.schema.payments"
            ),
            expected_change_type="metric_semantic",
            expected_confidence_min=0.7,
            expected_full_rebuild=True,
        ),
        GoldDatasetEntry(
            id="metric_006",
            category="metric_semantic",
            old_sql=("SELECT category, MAX(price) AS top_price " "FROM catalog.schema.products GROUP BY category"),
            new_sql=("SELECT category, MIN(price) AS top_price " "FROM catalog.schema.products GROUP BY category"),
            expected_change_type="metric_semantic",
            expected_confidence_min=0.8,
            expected_full_rebuild=True,
        ),
        GoldDatasetEntry(
            id="metric_007",
            category="metric_semantic",
            old_sql=("SELECT store_id, SUM(sales) AS total_sales " "FROM catalog.schema.daily_sales GROUP BY store_id"),
            new_sql=(
                "SELECT store_id, region, SUM(sales) AS total_sales "
                "FROM catalog.schema.daily_sales GROUP BY store_id, region"
            ),
            expected_change_type="metric_semantic",
            expected_confidence_min=0.7,
            expected_full_rebuild=True,
        ),
        GoldDatasetEntry(
            id="metric_008",
            category="metric_semantic",
            old_sql=(
                "SELECT id, amount, "
                "  ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY created_at DESC) AS rn "
                "FROM catalog.schema.transactions"
            ),
            new_sql=(
                "SELECT id, amount, "
                "  RANK() OVER (PARTITION BY user_id ORDER BY created_at DESC) AS rn "
                "FROM catalog.schema.transactions"
            ),
            expected_change_type="metric_semantic",
            expected_confidence_min=0.7,
            expected_full_rebuild=True,
        ),
        # =================================================================
        # PARTITION_SHIFT (5 entries) -- partition column/expression changes
        # =================================================================
        GoldDatasetEntry(
            id="partition_001",
            category="partition_shift",
            old_sql=("SELECT order_id, order_date, total " "FROM catalog.schema.orders"),
            new_sql=(
                "SELECT order_id, date_trunc('month', order_date) AS order_month, total " "FROM catalog.schema.orders"
            ),
            expected_change_type="partition_shift",
            expected_confidence_min=0.6,
            expected_full_rebuild=True,
        ),
        GoldDatasetEntry(
            id="partition_002",
            category="partition_shift",
            old_sql=("SELECT id, created_date, amount " "FROM catalog.schema.payments"),
            new_sql=(
                "SELECT id, YEAR(created_date) AS pay_year, MONTH(created_date) AS pay_month, amount "
                "FROM catalog.schema.payments"
            ),
            expected_change_type="partition_shift",
            expected_confidence_min=0.6,
            expected_full_rebuild=True,
        ),
        GoldDatasetEntry(
            id="partition_003",
            category="partition_shift",
            old_sql=("SELECT event_id, event_ts, event_type " "FROM catalog.schema.events"),
            new_sql=("SELECT event_id, DATE(event_ts) AS event_date, event_type " "FROM catalog.schema.events"),
            expected_change_type="partition_shift",
            expected_confidence_min=0.6,
            expected_full_rebuild=True,
        ),
        GoldDatasetEntry(
            id="partition_004",
            category="partition_shift",
            old_sql=("SELECT id, ts, region, value " "FROM catalog.schema.sensor_data"),
            new_sql=(
                "SELECT id, date_trunc('hour', ts) AS hour_bucket, region, value " "FROM catalog.schema.sensor_data"
            ),
            expected_change_type="partition_shift",
            expected_confidence_min=0.6,
            expected_full_rebuild=True,
        ),
        GoldDatasetEntry(
            id="partition_005",
            category="partition_shift",
            old_sql=("SELECT log_id, log_date, severity, message " "FROM catalog.schema.app_logs"),
            new_sql=(
                "SELECT log_id, date_trunc('week', log_date) AS log_week, severity, message "
                "FROM catalog.schema.app_logs"
            ),
            expected_change_type="partition_shift",
            expected_confidence_min=0.6,
            expected_full_rebuild=True,
        ),
        # =================================================================
        # MIXED / EDGE CASES (9 entries)
        # =================================================================
        GoldDatasetEntry(
            id="edge_001",
            category="edge_case",
            old_sql="",
            new_sql=(
                "SELECT order_id, customer_id, total_amount, order_date "
                "FROM catalog.schema.orders WHERE status = 'completed'"
            ),
            expected_change_type="non_breaking",
            expected_confidence_min=0.5,
            expected_full_rebuild=False,
        ),
        GoldDatasetEntry(
            id="edge_002",
            category="edge_case",
            old_sql=(
                "WITH base AS (\n"
                "  SELECT o.order_id, o.total, c.segment\n"
                "  FROM catalog.schema.orders o\n"
                "  JOIN catalog.schema.customers c ON o.customer_id = c.id\n"
                "), enriched AS (\n"
                "  SELECT order_id, total, segment,\n"
                "    CASE WHEN total > 1000 THEN 'high' ELSE 'low' END AS tier\n"
                "  FROM base\n"
                ")\n"
                "SELECT order_id, total, segment, tier FROM enriched"
            ),
            new_sql=(
                "WITH base AS (\n"
                "  SELECT o.order_id, o.total, c.segment\n"
                "  FROM catalog.schema.orders o\n"
                "  JOIN catalog.schema.customers c ON o.customer_id = c.id\n"
                "), enriched AS (\n"
                "  SELECT order_id, total, segment,\n"
                "    CASE WHEN total > 500 THEN 'high' ELSE 'low' END AS tier\n"
                "  FROM base\n"
                ")\n"
                "SELECT order_id, total, segment, tier FROM enriched"
            ),
            expected_change_type="breaking",
            expected_confidence_min=0.6,
            expected_full_rebuild=True,
        ),
        GoldDatasetEntry(
            id="edge_003",
            category="edge_case",
            old_sql=("SELECT id, name FROM catalog.schema.products"),
            new_sql=("SELECT id, name FROM catalog.schema.products"),
            expected_change_type="cosmetic",
            expected_confidence_min=0.95,
            expected_full_rebuild=False,
        ),
        GoldDatasetEntry(
            id="edge_004",
            category="edge_case",
            old_sql=("SELECT * FROM catalog.schema.users"),
            new_sql=("SELECT id, name, email, created_at FROM catalog.schema.users"),
            expected_change_type="non_breaking",
            expected_confidence_min=0.5,
            expected_full_rebuild=False,
            expected_suggestion_types=["select_star"],
        ),
        GoldDatasetEntry(
            id="edge_005",
            category="edge_case",
            old_sql=("SELECT DISTINCT customer_id, email FROM catalog.schema.customers"),
            new_sql=("SELECT customer_id, email FROM catalog.schema.customers"),
            expected_change_type="metric_semantic",
            expected_confidence_min=0.6,
            expected_full_rebuild=True,
        ),
        GoldDatasetEntry(
            id="edge_006",
            category="edge_case",
            old_sql=(
                "SELECT o.id, o.total,\n"
                "  SUM(o.total) OVER (PARTITION BY o.customer_id ORDER BY o.order_date) AS cumulative,\n"
                "  c.name\n"
                "FROM catalog.schema.orders o\n"
                "JOIN catalog.schema.customers c ON o.customer_id = c.id\n"
                "WHERE o.status = 'completed'\n"
                "ORDER BY o.order_date"
            ),
            new_sql=(
                "SELECT o.id, o.total,\n"
                "  AVG(o.total) OVER (PARTITION BY o.customer_id ORDER BY o.order_date) AS cumulative,\n"
                "  c.name\n"
                "FROM catalog.schema.orders o\n"
                "JOIN catalog.schema.customers c ON o.customer_id = c.id\n"
                "WHERE o.status = 'completed'\n"
                "ORDER BY o.order_date"
            ),
            expected_change_type="metric_semantic",
            expected_confidence_min=0.7,
            expected_full_rebuild=True,
        ),
        GoldDatasetEntry(
            id="edge_007",
            category="edge_case",
            old_sql=("SELECT id, amount, category FROM catalog.schema.expenses " "WHERE category = 'travel'"),
            new_sql=(
                "SELECT id, amount, category FROM catalog.schema.expenses " "WHERE category = 'travel' AND amount > 50"
            ),
            expected_change_type="non_breaking",
            expected_confidence_min=0.6,
            expected_full_rebuild=False,
        ),
        GoldDatasetEntry(
            id="edge_008",
            category="edge_case",
            old_sql=(
                "SELECT region, SUM(revenue) AS total_revenue,\n"
                "  COUNT(*) AS txn_count\n"
                "FROM catalog.schema.sales\n"
                "GROUP BY region"
            ),
            new_sql=(
                "SELECT region, SUM(revenue) AS total_revenue,\n"
                "  COUNT(*) AS txn_count,\n"
                "  AVG(revenue) AS avg_revenue\n"
                "FROM catalog.schema.sales\n"
                "GROUP BY region"
            ),
            schema_diff={"added": ["avg_revenue"]},
            expected_change_type="non_breaking",
            expected_confidence_min=0.6,
            expected_full_rebuild=False,
        ),
        GoldDatasetEntry(
            id="edge_009",
            category="edge_case",
            old_sql=("SELECT user_id, action, ts FROM catalog.schema.activity_log " "WHERE ts >= '2024-01-01'"),
            new_sql=(
                "SELECT user_id, action, ts, "
                "  LAG(ts) OVER (PARTITION BY user_id ORDER BY ts) AS prev_ts, "
                "  LEAD(ts) OVER (PARTITION BY user_id ORDER BY ts) AS next_ts "
                "FROM catalog.schema.activity_log "
                "WHERE ts >= '2024-01-01'"
            ),
            schema_diff={"added": ["prev_ts", "next_ts"]},
            expected_change_type="non_breaking",
            expected_confidence_min=0.6,
            expected_full_rebuild=False,
        ),
    ]

    def get_all(self) -> list[GoldDatasetEntry]:
        """Return all entries in the dataset."""
        return list(self.ENTRIES)

    def get_by_category(self, category: str) -> list[GoldDatasetEntry]:
        """Return entries filtered by category."""
        return [e for e in self.ENTRIES if e.category == category]

    @property
    def categories(self) -> list[str]:
        """Return sorted list of unique categories."""
        return sorted({e.category for e in self.ENTRIES})

    @property
    def size(self) -> int:
        """Return total number of entries."""
        return len(self.ENTRIES)
