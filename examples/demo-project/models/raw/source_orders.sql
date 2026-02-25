-- name: raw.source_orders
-- kind: FULL_REFRESH
-- materialization: TABLE
-- owner: data-platform
-- tags: raw, orders, source

SELECT
    order_id,
    customer_id,
    order_date,
    status,
    total_amount,
    currency,
    payment_method,
    created_at
FROM source_system.raw_orders
