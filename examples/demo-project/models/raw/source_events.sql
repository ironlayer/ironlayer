-- name: raw.source_events
-- kind: FULL_REFRESH
-- materialization: TABLE
-- owner: data-platform
-- tags: raw, events, source

SELECT
    event_id,
    user_id,
    event_type,
    event_timestamp,
    properties,
    created_at,
    _ingested_at
FROM source_system.raw_events
WHERE _ingested_at >= '{{ start_date }}'
    AND _ingested_at < '{{ end_date }}'
