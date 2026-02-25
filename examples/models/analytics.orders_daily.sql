-- name: analytics.orders_daily
-- kind: INCREMENTAL_BY_TIME_RANGE
-- materialization: INSERT_OVERWRITE
-- time_column: order_date
-- partition_by: order_date
-- owner: analytics
-- tags: analytics, orders, sla
-- dependencies: raw.events_enriched

SELECT
    DATE(event_timestamp) AS order_date,
    COUNT(DISTINCT event_id) AS total_orders,
    COUNT(DISTINCT user_id) AS unique_customers,
    SUM(CAST(properties:amount AS DOUBLE)) AS total_revenue,
    AVG(CAST(properties:amount AS DOUBLE)) AS avg_order_value
FROM {{ ref('raw.events_enriched') }}
WHERE event_type = 'purchase'
    AND event_timestamp >= '{{ start_date }}'
    AND event_timestamp < '{{ end_date }}'
GROUP BY DATE(event_timestamp)
