-- name: analytics.revenue_summary
-- kind: FULL_REFRESH
-- materialization: TABLE
-- owner: analytics
-- tags: analytics, revenue, executive-dashboard
-- dependencies: analytics.orders_daily, analytics.customer_lifetime_value

SELECT
    o.order_date,
    o.customer_country,
    o.total_orders,
    o.unique_customers,
    o.total_revenue,
    o.avg_order_value,
    o.completed_orders,
    o.refunded_orders,
    clv.total_customers,
    clv.avg_lifetime_value,
    o.total_revenue / NULLIF(clv.total_customers, 0) AS revenue_per_customer
FROM {{ ref('analytics.orders_daily') }} o
CROSS JOIN (
    SELECT
        COUNT(DISTINCT customer_id) AS total_customers,
        AVG(lifetime_value) AS avg_lifetime_value
    FROM {{ ref('analytics.customer_lifetime_value') }}
) clv
ORDER BY o.order_date DESC
