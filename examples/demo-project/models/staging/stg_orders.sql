-- name: staging.stg_orders
-- kind: INCREMENTAL_BY_TIME_RANGE
-- materialization: INSERT_OVERWRITE
-- time_column: order_date
-- owner: data-platform
-- tags: staging, orders
-- dependencies: raw.source_orders

SELECT
    o.order_id,
    o.customer_id,
    o.order_date,
    o.status,
    o.total_amount,
    o.currency,
    o.payment_method,
    c.country AS customer_country,
    c.segment AS customer_segment
FROM {{ ref('raw.source_orders') }} o
LEFT JOIN source_system.customers c
    ON o.customer_id = c.customer_id
WHERE o.order_date >= '{{ start_date }}'
    AND o.order_date < '{{ end_date }}'
