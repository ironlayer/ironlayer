"""Tests for the SQL toolkit factory and singleton behavior."""

from __future__ import annotations

import threading

from core_engine.sql_toolkit import get_sql_toolkit, register_implementation, reset_toolkit
from core_engine.sql_toolkit._protocols import SqlToolkit
from core_engine.sql_toolkit.impl.sqlglot_impl import SqlGlotToolkit


class TestFactory:
    """Factory function and singleton lifecycle."""

    def setup_method(self) -> None:
        reset_toolkit()

    def teardown_method(self) -> None:
        reset_toolkit()

    def test_default_is_sqlglot(self) -> None:
        tk = get_sql_toolkit()
        assert isinstance(tk, SqlGlotToolkit)

    def test_singleton_identity(self) -> None:
        tk1 = get_sql_toolkit()
        tk2 = get_sql_toolkit()
        assert tk1 is tk2

    def test_reset_clears_singleton(self) -> None:
        tk1 = get_sql_toolkit()
        reset_toolkit()
        tk2 = get_sql_toolkit()
        assert tk1 is not tk2

    def test_register_custom_implementation(self) -> None:
        class FakeToolkit:
            parser = None
            renderer = None
            scope_analyzer = None
            transpiler = None
            normalizer = None
            differ = None
            safety_guard = None
            rewriter = None

        fake = FakeToolkit()
        register_implementation(lambda: fake)  # type: ignore[arg-type, return-value]
        tk = get_sql_toolkit()
        assert tk is fake  # type: ignore[comparison-overlap]

    def test_register_replaces_existing(self) -> None:
        tk1 = get_sql_toolkit()
        assert isinstance(tk1, SqlGlotToolkit)

        register_implementation(lambda: SqlGlotToolkit())
        tk2 = get_sql_toolkit()
        assert tk2 is not tk1

    def test_thread_safety(self) -> None:
        """Multiple threads calling get_sql_toolkit() get the same instance."""
        results: list[object] = []
        barrier = threading.Barrier(10)

        def _get() -> None:
            barrier.wait()
            results.append(get_sql_toolkit())

        threads = [threading.Thread(target=_get) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 10
        assert all(r is results[0] for r in results)

    def test_protocol_compliance(self) -> None:
        """SqlGlotToolkit satisfies the SqlToolkit protocol at runtime."""
        tk = get_sql_toolkit()
        assert isinstance(tk, SqlToolkit)
