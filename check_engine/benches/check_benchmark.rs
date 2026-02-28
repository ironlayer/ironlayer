//! Criterion benchmarks for the IronLayer Check Engine.
//!
//! Benchmarks measure cold and warm check times for synthetic projects
//! of varying sizes (100, 500, 1000 models).

use criterion::{criterion_group, criterion_main, Criterion};

fn bench_placeholder(c: &mut Criterion) {
    c.bench_function("placeholder", |b| {
        b.iter(|| {
            // Phase 2 will add real benchmarks with synthetic projects
            std::hint::black_box(1 + 1)
        })
    });
}

criterion_group!(benches, bench_placeholder);
criterion_main!(benches);
