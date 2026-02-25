-- name: analytics.user_metrics
-- kind: FULL_REFRESH
-- materialization: TABLE
-- owner: analytics
-- tags: analytics, users, dashboard
-- dependencies: raw.events_enriched

SELECT
    user_id,
    country,
    segment,
    COUNT(DISTINCT event_id) AS total_events,
    COUNT(DISTINCT CASE WHEN event_type = 'purchase' THEN event_id END) AS total_purchases,
    SUM(CASE WHEN event_type = 'purchase' THEN CAST(properties:amount AS DOUBLE) ELSE 0 END) AS lifetime_value,
    MIN(event_timestamp) AS first_activity,
    MAX(event_timestamp) AS last_activity,
    DATEDIFF(MAX(event_timestamp), MIN(event_timestamp)) AS active_days
FROM {{ ref('raw.events_enriched') }}
GROUP BY user_id, country, segment
