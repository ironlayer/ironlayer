-- name: staging.stg_customers
-- kind: FULL_REFRESH
-- materialization: TABLE
-- owner: data-platform
-- tags: staging, customers

SELECT
    customer_id,
    email,
    full_name,
    country,
    segment,
    signup_date,
    CASE
        WHEN last_order_date >= DATEADD(DAY, -90, CURRENT_DATE()) THEN 'active'
        WHEN last_order_date >= DATEADD(DAY, -365, CURRENT_DATE()) THEN 'dormant'
        ELSE 'churned'
    END AS lifecycle_stage
FROM source_system.customers
