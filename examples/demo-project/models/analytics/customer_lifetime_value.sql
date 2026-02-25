-- name: analytics.customer_lifetime_value
-- kind: FULL_REFRESH
-- materialization: TABLE
-- unique_key: customer_id
-- owner: analytics
-- tags: analytics, customers, clv
-- dependencies: staging.stg_orders, staging.stg_customers

SELECT
    c.customer_id,
    c.full_name,
    c.country,
    c.segment,
    c.lifecycle_stage,
    c.signup_date,
    COUNT(DISTINCT o.order_id) AS total_orders,
    SUM(o.total_amount) AS lifetime_value,
    AVG(o.total_amount) AS avg_order_value,
    MIN(o.order_date) AS first_order_date,
    MAX(o.order_date) AS last_order_date,
    DATEDIFF(MAX(o.order_date), MIN(o.order_date)) AS customer_tenure_days,
    CASE
        WHEN SUM(o.total_amount) >= 10000 THEN 'platinum'
        WHEN SUM(o.total_amount) >= 5000 THEN 'gold'
        WHEN SUM(o.total_amount) >= 1000 THEN 'silver'
        ELSE 'bronze'
    END AS value_tier
FROM {{ ref('staging.stg_customers') }} c
LEFT JOIN {{ ref('staging.stg_orders') }} o
    ON c.customer_id = o.customer_id
GROUP BY
    c.customer_id,
    c.full_name,
    c.country,
    c.segment,
    c.lifecycle_stage,
    c.signup_date
