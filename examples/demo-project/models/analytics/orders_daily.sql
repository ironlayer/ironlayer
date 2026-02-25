-- name: analytics.orders_daily
-- kind: INCREMENTAL_BY_TIME_RANGE
-- materialization: INSERT_OVERWRITE
-- time_column: order_date
-- owner: analytics
-- tags: analytics, orders, sla
-- dependencies: staging.stg_orders

SELECT
    order_date,
    customer_country,
    customer_segment,
    COUNT(DISTINCT order_id) AS total_orders,
    COUNT(DISTINCT customer_id) AS unique_customers,
    SUM(total_amount) AS total_revenue,
    AVG(total_amount) AS avg_order_value,
    COUNT(CASE WHEN status = 'completed' THEN 1 END) AS completed_orders,
    COUNT(CASE WHEN status = 'refunded' THEN 1 END) AS refunded_orders
FROM {{ ref('staging.stg_orders') }}
WHERE order_date >= '{{ start_date }}'
    AND order_date < '{{ end_date }}'
GROUP BY order_date, customer_country, customer_segment
