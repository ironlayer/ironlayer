-- name: analytics.user_metrics
-- kind: FULL_REFRESH
-- materialization: TABLE
-- owner: analytics
-- tags: analytics, users, dashboard
-- dependencies: staging.stg_events

SELECT
    user_id,
    country,
    segment,
    COUNT(DISTINCT event_id) AS total_events,
    COUNT(DISTINCT CASE WHEN event_type = 'purchase' THEN event_id END) AS total_purchases,
    COUNT(DISTINCT CASE WHEN event_type = 'page_view' THEN event_id END) AS total_page_views,
    SUM(CASE
        WHEN event_type = 'purchase'
        THEN CAST(properties:amount AS DOUBLE)
        ELSE 0
    END) AS total_spend,
    MIN(event_timestamp) AS first_activity,
    MAX(event_timestamp) AS last_activity,
    DATEDIFF(MAX(event_timestamp), MIN(event_timestamp)) AS active_days
FROM {{ ref('staging.stg_events') }}
GROUP BY user_id, country, segment
