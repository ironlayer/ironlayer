-- name: analytics.revenue_summary
-- kind: FULL_REFRESH
-- materialization: TABLE
-- owner: analytics
-- tags: analytics, revenue, executive-dashboard
-- dependencies: analytics.orders_daily, analytics.user_metrics

SELECT
    o.order_date,
    o.total_orders,
    o.unique_customers,
    o.total_revenue,
    o.avg_order_value,
    um.total_users,
    um.avg_lifetime_value,
    o.total_revenue / NULLIF(um.total_users, 0) AS revenue_per_user
FROM {{ ref('analytics.orders_daily') }} o
CROSS JOIN (
    SELECT
        COUNT(DISTINCT user_id) AS total_users,
        AVG(lifetime_value) AS avg_lifetime_value
    FROM {{ ref('analytics.user_metrics') }}
) um
ORDER BY o.order_date DESC
