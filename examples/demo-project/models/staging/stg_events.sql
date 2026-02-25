-- name: staging.stg_events
-- kind: INCREMENTAL_BY_TIME_RANGE
-- materialization: TABLE
-- time_column: event_timestamp
-- owner: data-platform
-- tags: staging, events, enriched
-- dependencies: raw.source_events

SELECT
    e.event_id,
    e.user_id,
    e.event_type,
    e.event_timestamp,
    e.properties,
    u.country,
    u.segment,
    u.signup_date
FROM {{ ref('raw.source_events') }} e
LEFT JOIN dim_users u
    ON e.user_id = u.user_id
WHERE e.event_timestamp >= '{{ start_date }}'
    AND e.event_timestamp < '{{ end_date }}'
