//! Criterion benchmarks for the IronLayer Check Engine.
//!
//! Benchmarks measure cold and warm check times for synthetic projects
//! of varying sizes (100, 500, 1000 models). Synthetic models include
//! headers, SQL bodies, and ref() macros to exercise all Phase 2 checkers.

use std::fs;
use std::path::PathBuf;

use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion};
use ironlayer_check_engine::config::CheckConfig;
use ironlayer_check_engine::engine::CheckEngine;

/// Create a synthetic IronLayer project with `n` SQL model files.
///
/// Returns the path to the temporary project directory. Caller must
/// clean up via [`std::fs::remove_dir_all`].
fn create_synthetic_project(n: usize) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("ironlayer_bench_{}", std::process::id()));
    let models_dir = dir.join("models");
    let staging_dir = models_dir.join("staging");
    let marts_dir = models_dir.join("marts");

    fs::create_dir_all(&staging_dir).expect("create staging dir");
    fs::create_dir_all(&marts_dir).expect("create marts dir");

    // Create n models: half staging, half marts
    let half = n / 2;

    for i in 0..half {
        let name = format!("stg_model_{}", i);
        let content = format!(
            "-- name: {name}\n\
             -- kind: FULL_REFRESH\n\
             -- materialization: TABLE\n\
             -- owner: analytics\n\
             -- tags: staging, raw\n\
             \n\
             SELECT\n\
                 id,\n\
                 created_at,\n\
                 updated_at,\n\
                 name,\n\
                 email,\n\
                 status\n\
             FROM raw_db.raw_schema.source_table_{i}\n\
             WHERE created_at >= '2024-01-01'\n\
               AND status != 'deleted'\n"
        );
        let path = staging_dir.join(format!("{}.sql", name));
        fs::write(&path, &content).expect("write staging model");
    }

    for i in 0..half {
        // Mart models ref staging models
        let name = format!("fct_model_{}", i);
        let ref_idx = i % half;
        let content = format!(
            "-- name: {name}\n\
             -- kind: FULL_REFRESH\n\
             -- materialization: TABLE\n\
             -- owner: analytics\n\
             -- tags: marts, fact\n\
             \n\
             SELECT\n\
                 a.id,\n\
                 a.name,\n\
                 a.email,\n\
                 COUNT(b.order_id) AS total_orders,\n\
                 SUM(b.amount) AS total_amount\n\
             FROM {{{{ ref('stg_model_{ref_idx}') }}}} AS a\n\
             LEFT JOIN {{{{ ref('stg_model_{alt_ref}') }}}} AS b\n\
                 ON a.id = b.customer_id\n\
             GROUP BY a.id, a.name, a.email\n\
             HAVING COUNT(b.order_id) > 0\n",
            alt_ref = (i + 1) % half
        );
        let path = marts_dir.join(format!("{}.sql", name));
        fs::write(&path, &content).expect("write mart model");
    }

    // If n is odd, add one more staging model
    if n % 2 != 0 {
        let name = format!("stg_model_{}", half);
        let content = format!(
            "-- name: {name}\n\
             -- kind: FULL_REFRESH\n\
             \n\
             SELECT 1 AS dummy\n"
        );
        let path = staging_dir.join(format!("{}.sql", name));
        fs::write(&path, &content).expect("write extra staging model");
    }

    dir
}

fn bench_check_cold(c: &mut Criterion) {
    let mut group = c.benchmark_group("check_cold");
    group.sample_size(10);

    for &size in &[100, 500] {
        let dir = create_synthetic_project(size);
        let config = CheckConfig::default();
        let engine = CheckEngine::new(config);

        group.bench_with_input(BenchmarkId::from_parameter(size), &size, |b, _| {
            b.iter(|| {
                let result = engine.check(&dir);
                std::hint::black_box(result);
            })
        });

        let _ = fs::remove_dir_all(&dir);
    }

    group.finish();
}

fn bench_check_warm(c: &mut Criterion) {
    let mut group = c.benchmark_group("check_warm");
    group.sample_size(10);

    for &size in &[100, 500] {
        let dir = create_synthetic_project(size);
        let config = CheckConfig::default();
        let engine = CheckEngine::new(config);

        // Prime the cache with an initial run
        let _ = engine.check(&dir);

        group.bench_with_input(BenchmarkId::from_parameter(size), &size, |b, _| {
            b.iter(|| {
                let result = engine.check(&dir);
                std::hint::black_box(result);
            })
        });

        let _ = fs::remove_dir_all(&dir);
    }

    group.finish();
}

fn bench_lexer(c: &mut Criterion) {
    let sql = "SELECT\n\
                   a.id,\n\
                   a.name,\n\
                   b.order_id,\n\
                   COUNT(*) AS cnt,\n\
                   SUM(b.amount) AS total\n\
               FROM {{ ref('stg_orders') }} AS a\n\
               LEFT JOIN {{ ref('stg_items') }} AS b\n\
                   ON a.id = b.customer_id\n\
               WHERE a.status != 'deleted'\n\
                 AND b.created_at >= '2024-01-01'\n\
               GROUP BY a.id, a.name, b.order_id\n\
               HAVING COUNT(*) > 1\n\
               ORDER BY total DESC\n\
               LIMIT 100;\n";

    c.bench_function("lexer_tokenize", |b| {
        b.iter(|| {
            let tokens = ironlayer_check_engine::sql_lexer::tokenize(std::hint::black_box(sql));
            std::hint::black_box(tokens);
        })
    });
}

criterion_group!(benches, bench_check_cold, bench_check_warm, bench_lexer);
criterion_main!(benches);
