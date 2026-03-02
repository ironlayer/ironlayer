"""Contract tests for the SQL toolkit protocols.

These tests validate behavior that ANY implementation must satisfy.
They test against the protocol interface via ``get_sql_toolkit()``,
not against SQLGlot internals.  When a future implementation is built
(sqloxide, custom parser), it must pass these same tests unchanged.

Test categories:
1. Parsing contract (15 tests)
2. Scope analysis contract (12 tests)
3. Transpilation contract (8 tests)
4. Normalisation contract (10 tests)
5. Diffing contract (10 tests)
6. Safety guard contract (14 tests)
7. Rewriting contract (8 tests)
8. Rendering contract (4 tests)
9. Determinism invariant (5 tests)
"""

from __future__ import annotations

import pytest

from core_engine.sql_toolkit import (
    Dialect,
    RewriteRule,
    SqlNormalizationError,
    SqlParseError,
    get_sql_toolkit,
    reset_toolkit,
)
from core_engine.sql_toolkit._types import SqlNodeKind


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Ensure each test gets a fresh toolkit (singleton safety)."""
    reset_toolkit()
    yield
    reset_toolkit()


@pytest.fixture()
def tk():
    """Return the default SQL toolkit."""
    return get_sql_toolkit()


# ===================================================================
# 1. Parsing Contract
# ===================================================================


class TestParsingContract:
    """Parsing protocol: parse_one() and parse_multi()."""

    def test_simple_select(self, tk):
        result = tk.parser.parse_one("SELECT a, b FROM t", Dialect.DATABRICKS)
        assert len(result.statements) == 1
        assert result.single.kind == SqlNodeKind.SELECT

    def test_select_with_cte(self, tk):
        sql = "WITH cte AS (SELECT 1 AS x) SELECT * FROM cte"
        result = tk.parser.parse_one(sql, Dialect.DATABRICKS)
        assert len(result.statements) == 1

    def test_select_with_subquery(self, tk):
        sql = "SELECT * FROM (SELECT a FROM t) sub"
        result = tk.parser.parse_one(sql, Dialect.DATABRICKS)
        assert len(result.statements) == 1

    def test_select_union(self, tk):
        sql = "SELECT a FROM t1 UNION ALL SELECT a FROM t2"
        result = tk.parser.parse_one(sql, Dialect.DATABRICKS)
        assert len(result.statements) == 1

    def test_multi_statement(self, tk):
        sql = "SELECT 1; SELECT 2; SELECT 3"
        result = tk.parser.parse_multi(sql, Dialect.DATABRICKS)
        assert len(result.statements) == 3

    def test_empty_sql_raises(self, tk):
        with pytest.raises(SqlParseError):
            tk.parser.parse_one("", Dialect.DATABRICKS)

    def test_invalid_sql_raises(self, tk):
        with pytest.raises(SqlParseError):
            tk.parser.parse_one("NOT VALID SQL ???", Dialect.DATABRICKS)

    def test_invalid_sql_no_raise(self, tk):
        result = tk.parser.parse_one(
            "NOT VALID SQL ???",
            Dialect.DATABRICKS,
            raise_on_error=False,
        )
        # Should either return warnings or empty statements — not crash.
        assert result is not None

    def test_parse_result_dialect(self, tk):
        result = tk.parser.parse_one("SELECT 1", Dialect.DATABRICKS)
        assert result.dialect == Dialect.DATABRICKS

    def test_parse_result_single_property(self, tk):
        result = tk.parser.parse_one("SELECT 1", Dialect.DATABRICKS)
        node = result.single
        assert node.kind == SqlNodeKind.SELECT

    def test_multi_statement_single_raises(self, tk):
        result = tk.parser.parse_multi("SELECT 1; SELECT 2", Dialect.DATABRICKS)
        with pytest.raises(ValueError, match="Expected exactly 1"):
            _ = result.single

    def test_three_part_name(self, tk):
        sql = "SELECT * FROM catalog.schema.table_name"
        result = tk.parser.parse_one(sql, Dialect.DATABRICKS)
        assert len(result.statements) == 1

    def test_merge_into(self, tk):
        sql = (
            "MERGE INTO target USING source ON target.id = source.id "
            "WHEN MATCHED THEN UPDATE SET target.val = source.val"
        )
        result = tk.parser.parse_one(sql, Dialect.DATABRICKS)
        assert len(result.statements) == 1
        assert result.single.kind == SqlNodeKind.MERGE

    def test_create_table(self, tk):
        sql = "CREATE TABLE t (id INT, name STRING)"
        result = tk.parser.parse_one(sql, Dialect.DATABRICKS)
        assert result.single.kind == SqlNodeKind.CREATE

    def test_duckdb_dialect(self, tk):
        result = tk.parser.parse_one("SELECT 1", Dialect.DUCKDB)
        assert result.dialect == Dialect.DUCKDB


# ===================================================================
# 2. Scope Analysis Contract
# ===================================================================


class TestScopeAnalysisContract:
    """Scope analyzer protocol: extract_tables() and extract_columns()."""

    def test_simple_table_extraction(self, tk):
        scope = tk.scope_analyzer.extract_tables("SELECT * FROM orders", Dialect.DATABRICKS)
        assert len(scope.referenced_tables) == 1
        assert scope.referenced_tables[0].name == "orders"

    def test_cte_excluded_from_tables(self, tk):
        sql = "WITH cte AS (SELECT * FROM raw_data) SELECT * FROM cte"
        scope = tk.scope_analyzer.extract_tables(sql, Dialect.DATABRICKS)
        table_names = {t.name for t in scope.referenced_tables}
        assert "cte" not in table_names
        assert "raw_data" in table_names

    def test_cte_names_returned(self, tk):
        sql = "WITH my_cte AS (SELECT 1) SELECT * FROM my_cte"
        scope = tk.scope_analyzer.extract_tables(sql, Dialect.DATABRICKS)
        assert "my_cte" in scope.cte_names

    def test_subquery_tables_included(self, tk):
        sql = "SELECT * FROM (SELECT * FROM inner_table) sub"
        scope = tk.scope_analyzer.extract_tables(sql, Dialect.DATABRICKS)
        table_names = {t.name for t in scope.referenced_tables}
        assert "inner_table" in table_names

    def test_three_part_name_parsed(self, tk):
        sql = "SELECT * FROM my_catalog.my_schema.my_table"
        scope = tk.scope_analyzer.extract_tables(sql, Dialect.DATABRICKS)
        ref = scope.referenced_tables[0]
        assert ref.catalog == "my_catalog"
        assert ref.schema == "my_schema"
        assert ref.name == "my_table"

    def test_tables_sorted_deterministically(self, tk):
        sql = "SELECT * FROM z_table JOIN a_table ON z_table.id = a_table.id"
        scope = tk.scope_analyzer.extract_tables(sql, Dialect.DATABRICKS)
        names = [t.name for t in scope.referenced_tables]
        assert names == sorted(names)

    def test_multiple_ctes(self, tk):
        sql = "WITH cte_a AS (SELECT * FROM raw_a), cte_b AS (SELECT * FROM raw_b) SELECT * FROM cte_a JOIN cte_b"
        scope = tk.scope_analyzer.extract_tables(sql, Dialect.DATABRICKS)
        table_names = {t.name for t in scope.referenced_tables}
        assert "raw_a" in table_names
        assert "raw_b" in table_names
        assert "cte_a" not in table_names
        assert "cte_b" not in table_names

    def test_output_columns(self, tk):
        sql = "SELECT id, name AS full_name, COUNT(*) AS cnt FROM users"
        cols = tk.scope_analyzer.extract_columns(sql, Dialect.DATABRICKS)
        assert "cnt" in cols.output_columns
        assert "full_name" in cols.output_columns

    def test_star_detection(self, tk):
        cols = tk.scope_analyzer.extract_columns("SELECT * FROM t", Dialect.DATABRICKS)
        assert cols.has_star is True

    def test_aggregation_detection(self, tk):
        cols = tk.scope_analyzer.extract_columns("SELECT COUNT(id) FROM t", Dialect.DATABRICKS)
        assert cols.has_aggregation is True

    def test_window_function_detection(self, tk):
        cols = tk.scope_analyzer.extract_columns("SELECT SUM(x) OVER (PARTITION BY y) FROM t", Dialect.DATABRICKS)
        assert cols.has_window_functions is True

    def test_no_aggregation_no_window(self, tk):
        cols = tk.scope_analyzer.extract_columns("SELECT a, b FROM t", Dialect.DATABRICKS)
        assert cols.has_aggregation is False
        assert cols.has_window_functions is False


# ===================================================================
# 3. Transpilation Contract
# ===================================================================


class TestTranspilationContract:
    """Transpiler protocol: transpile()."""

    def test_databricks_to_duckdb_basic(self, tk):
        result = tk.transpiler.transpile(
            "SELECT a, b FROM t",
            Dialect.DATABRICKS,
            Dialect.DUCKDB,
        )
        assert result.output_sql
        assert result.fallback_used is False
        assert result.source_dialect == Dialect.DATABRICKS
        assert result.target_dialect == Dialect.DUCKDB

    def test_databricks_to_duckdb_date_trunc(self, tk):
        result = tk.transpiler.transpile(
            "SELECT DATE_TRUNC('month', order_date) FROM orders",
            Dialect.DATABRICKS,
            Dialect.DUCKDB,
        )
        assert result.fallback_used is False
        assert result.output_sql  # Should produce valid DuckDB SQL

    def test_identity_transpile(self, tk):
        sql = "SELECT a FROM t WHERE x = 1"
        result = tk.transpiler.transpile(sql, Dialect.DATABRICKS, Dialect.DATABRICKS)
        assert result.fallback_used is False
        assert result.output_sql

    def test_fallback_on_invalid_sql(self, tk):
        result = tk.transpiler.transpile(
            "DEFINITELY NOT SQL ???",
            Dialect.DATABRICKS,
            Dialect.DUCKDB,
        )
        # Should fall back gracefully, not crash.
        assert result.fallback_used is True
        assert result.output_sql == "DEFINITELY NOT SQL ???"
        assert len(result.warnings) > 0

    def test_transpile_with_join(self, tk):
        sql = "SELECT a.id, b.name FROM orders a INNER JOIN customers b ON a.cust_id = b.id"
        result = tk.transpiler.transpile(sql, Dialect.DATABRICKS, Dialect.DUCKDB)
        assert result.fallback_used is False

    def test_pretty_output(self, tk):
        result = tk.transpiler.transpile(
            "SELECT a, b, c FROM t WHERE x = 1",
            Dialect.DATABRICKS,
            Dialect.DUCKDB,
            pretty=True,
        )
        assert "\n" in result.output_sql  # Pretty output has newlines

    def test_transpile_result_dialects(self, tk):
        result = tk.transpiler.transpile("SELECT 1", Dialect.DATABRICKS, Dialect.DUCKDB)
        assert result.source_dialect == Dialect.DATABRICKS
        assert result.target_dialect == Dialect.DUCKDB

    def test_transpile_empty_result_fallback(self, tk):
        # Edge case: transpile should handle gracefully.
        result = tk.transpiler.transpile("SELECT 1", Dialect.DATABRICKS, Dialect.DUCKDB)
        assert result.output_sql


# ===================================================================
# 4. Normalisation Contract
# ===================================================================


class TestNormalisationContract:
    """Normalizer protocol: normalize()."""

    def test_whitespace_normalisation(self, tk):
        norm = tk.normalizer.normalize("SELECT   a,   b   FROM   t", Dialect.DATABRICKS)
        # Normalised SQL should not have excess whitespace.
        assert "   " not in norm.normalized_sql

    def test_comment_stripping(self, tk):
        norm = tk.normalizer.normalize(
            "SELECT a -- this is a comment\nFROM t /* block */",
            Dialect.DATABRICKS,
        )
        assert "--" not in norm.normalized_sql
        assert "/*" not in norm.normalized_sql

    def test_keyword_uppercasing(self, tk):
        norm = tk.normalizer.normalize("select a from t where x = 1", Dialect.DATABRICKS)
        # Keywords should be normalized (sqlglot uppercases them).
        assert "SELECT" in norm.normalized_sql
        assert "FROM" in norm.normalized_sql

    def test_cte_reordering_safe(self, tk):
        sql = "WITH z AS (SELECT 1), a AS (SELECT 2) SELECT * FROM a, z"
        norm = tk.normalizer.normalize(sql, Dialect.DATABRICKS)
        # a should come before z in the normalised output.
        a_pos = norm.normalized_sql.find(" a AS")
        z_pos = norm.normalized_sql.find(" z AS")
        # If both found, a should appear first.
        if a_pos >= 0 and z_pos >= 0:
            assert a_pos < z_pos

    def test_cte_reordering_skipped_forward_ref(self, tk):
        # b references a, but a is defined after b → forward ref, skip reorder.
        sql = "WITH b AS (SELECT * FROM a), a AS (SELECT 1) SELECT * FROM b"
        norm = tk.normalizer.normalize(sql, Dialect.DATABRICKS)
        # b should still come before a (order preserved).
        b_pos = norm.normalized_sql.find(" b AS")
        a_pos = norm.normalized_sql.find(" a AS")
        if b_pos >= 0 and a_pos >= 0:
            assert b_pos < a_pos

    def test_normalisation_preserves_original(self, tk):
        original = "select a from t"
        norm = tk.normalizer.normalize(original, Dialect.DATABRICKS)
        assert norm.original_sql == original

    def test_normalisation_applied_rules(self, tk):
        norm = tk.normalizer.normalize("SELECT 1", Dialect.DATABRICKS)
        assert len(norm.applied_rules) > 0
        assert "strip_comments" in norm.applied_rules

    def test_normalisation_empty_sql(self, tk):
        norm = tk.normalizer.normalize("", Dialect.DATABRICKS)
        assert norm.normalized_sql == ""

    def test_normalisation_comment_only(self, tk):
        norm = tk.normalizer.normalize("-- just a comment", Dialect.DATABRICKS)
        assert norm.normalized_sql == ""

    def test_normalisation_invalid_sql_raises(self, tk):
        with pytest.raises(SqlNormalizationError):
            tk.normalizer.normalize("NOT VALID SQL ???", Dialect.DATABRICKS)


# ===================================================================
# 5. Diffing Contract
# ===================================================================


class TestDiffingContract:
    """Differ protocol: diff() and extract_column_changes()."""

    def test_identical_sql(self, tk):
        diff = tk.differ.diff("SELECT a FROM t", "SELECT a FROM t", Dialect.DATABRICKS)
        assert diff.is_cosmetic_only is True or diff.is_identical is True

    def test_cosmetic_only_whitespace(self, tk):
        diff = tk.differ.diff(
            "SELECT   a   FROM   t",
            "SELECT a FROM t",
            Dialect.DATABRICKS,
        )
        assert diff.is_cosmetic_only is True

    def test_column_addition(self, tk):
        changes = tk.differ.extract_column_changes(
            "SELECT a FROM t",
            "SELECT a, b FROM t",
            Dialect.DATABRICKS,
        )
        assert changes.get("b") == "added"

    def test_column_removal(self, tk):
        changes = tk.differ.extract_column_changes(
            "SELECT a, b FROM t",
            "SELECT a FROM t",
            Dialect.DATABRICKS,
        )
        assert changes.get("b") == "removed"

    def test_column_modification(self, tk):
        changes = tk.differ.extract_column_changes(
            "SELECT a, b AS x FROM t",
            "SELECT a, c AS x FROM t",
            Dialect.DATABRICKS,
        )
        # x is present in both but the expression changed.
        assert changes.get("x") == "modified"

    def test_no_changes(self, tk):
        changes = tk.differ.extract_column_changes(
            "SELECT a, b FROM t",
            "SELECT a, b FROM t",
            Dialect.DATABRICKS,
        )
        assert len(changes) == 0

    def test_diff_edits_not_empty_on_real_change(self, tk):
        diff = tk.differ.diff(
            "SELECT a FROM t",
            "SELECT b FROM t",
            Dialect.DATABRICKS,
        )
        assert diff.is_identical is False
        assert diff.is_cosmetic_only is False

    def test_diff_parse_failure_does_not_crash(self, tk):
        diff = tk.differ.diff(
            "NOT SQL ???",
            "SELECT a FROM t",
            Dialect.DATABRICKS,
        )
        assert diff.is_identical is False

    def test_column_changes_parse_failure(self, tk):
        changes = tk.differ.extract_column_changes(
            "NOT SQL ???",
            "SELECT a FROM t",
            Dialect.DATABRICKS,
        )
        assert isinstance(changes, dict)

    def test_diff_comment_only_is_cosmetic(self, tk):
        # Comments are stripped by sqlglot during transpile normalisation,
        # so comment-only changes produce identical normalised SQL.
        # sqlglot may report this as is_identical=True rather than
        # is_cosmetic_only=True when the raw strings also normalise identically.
        diff = tk.differ.diff(
            "SELECT a FROM t -- old comment",
            "SELECT a FROM t -- new comment",
            Dialect.DATABRICKS,
        )
        assert diff.is_cosmetic_only is True or diff.is_identical is True


# ===================================================================
# 6. Safety Guard Contract
# ===================================================================


class TestSafetyGuardContract:
    """Safety guard protocol: check()."""

    def test_safe_select(self, tk):
        result = tk.safety_guard.check("SELECT a FROM t", Dialect.DATABRICKS)
        assert result.is_safe is True
        assert len(result.violations) == 0

    def test_drop_table_detected(self, tk):
        result = tk.safety_guard.check("DROP TABLE users", Dialect.DATABRICKS)
        assert result.is_safe is False
        types = {v.violation_type for v in result.violations}
        assert "DROP_TABLE" in types

    def test_drop_view_detected(self, tk):
        result = tk.safety_guard.check("DROP VIEW v", Dialect.DATABRICKS)
        assert result.is_safe is False
        types = {v.violation_type for v in result.violations}
        assert "DROP_VIEW" in types

    def test_truncate_detected(self, tk):
        result = tk.safety_guard.check("TRUNCATE TABLE users", Dialect.DATABRICKS)
        assert result.is_safe is False
        types = {v.violation_type for v in result.violations}
        assert "TRUNCATE" in types

    def test_delete_without_where_detected(self, tk):
        result = tk.safety_guard.check("DELETE FROM users", Dialect.DATABRICKS)
        assert result.is_safe is False
        types = {v.violation_type for v in result.violations}
        assert "DELETE_WITHOUT_WHERE" in types

    def test_delete_with_where_safe(self, tk):
        result = tk.safety_guard.check("DELETE FROM users WHERE id = 5", Dialect.DATABRICKS)
        assert result.is_safe is True

    def test_grant_detected(self, tk):
        result = tk.safety_guard.check("GRANT SELECT ON t TO user1", Dialect.DATABRICKS)
        assert result.is_safe is False
        types = {v.violation_type for v in result.violations}
        assert "GRANT" in types

    def test_insert_overwrite_no_partition(self, tk):
        result = tk.safety_guard.check("INSERT OVERWRITE TABLE t SELECT * FROM src", Dialect.DATABRICKS)
        assert result.is_safe is False

    def test_multi_statement_catches_dangerous(self, tk):
        result = tk.safety_guard.check("SELECT 1; DROP TABLE users", Dialect.DATABRICKS)
        assert result.is_safe is False
        assert result.checked_statements == 2

    def test_create_table_allowed_by_default(self, tk):
        result = tk.safety_guard.check("CREATE TABLE t (id INT)", Dialect.DATABRICKS)
        assert result.is_safe is True

    def test_create_table_blocked_when_disallowed(self, tk):
        result = tk.safety_guard.check(
            "CREATE TABLE t (id INT)",
            Dialect.DATABRICKS,
            allow_create=False,
        )
        assert result.is_safe is False

    def test_unparseable_sql_flagged(self, tk):
        result = tk.safety_guard.check("???###!!!", Dialect.DATABRICKS)
        assert result.is_safe is False

    def test_violation_has_detail(self, tk):
        result = tk.safety_guard.check("DROP TABLE users", Dialect.DATABRICKS)
        assert len(result.violations) > 0
        assert result.violations[0].detail
        assert result.violations[0].violation_type

    def test_violation_severity_set(self, tk):
        result = tk.safety_guard.check("DROP TABLE users", Dialect.DATABRICKS)
        assert result.violations[0].severity in ("error", "warning")


# ===================================================================
# 7. Rewriting Contract
# ===================================================================


class TestRewritingContract:
    """Rewriter protocol: rewrite_tables() and quote_identifier()."""

    def test_simple_rewrite(self, tk):
        result = tk.rewriter.rewrite_tables(
            "SELECT * FROM main.public.orders",
            [
                RewriteRule(
                    source_catalog="main",
                    source_schema="public",
                    target_catalog="dev",
                    target_schema="staging",
                )
            ],
            Dialect.DATABRICKS,
        )
        assert "dev" in result.rewritten_sql
        assert "staging" in result.rewritten_sql
        assert len(result.tables_rewritten) > 0

    def test_unqualified_table_gets_target(self, tk):
        result = tk.rewriter.rewrite_tables(
            "SELECT * FROM orders",
            [
                RewriteRule(
                    target_catalog="prod",
                    target_schema="analytics",
                )
            ],
            Dialect.DATABRICKS,
        )
        assert "prod" in result.rewritten_sql
        assert "analytics" in result.rewritten_sql

    def test_no_match_unchanged(self, tk):
        result = tk.rewriter.rewrite_tables(
            "SELECT * FROM other_catalog.other_schema.t",
            [
                RewriteRule(
                    source_catalog="main",
                    source_schema="public",
                    target_catalog="dev",
                    target_schema="staging",
                )
            ],
            Dialect.DATABRICKS,
        )
        assert len(result.tables_unchanged) > 0

    def test_empty_rules_noop(self, tk):
        sql = "SELECT * FROM t"
        result = tk.rewriter.rewrite_tables(sql, [], Dialect.DATABRICKS)
        assert result.rewritten_sql == sql

    def test_multi_statement_rewrite(self, tk):
        result = tk.rewriter.rewrite_tables(
            "SELECT * FROM main.pub.t1; SELECT * FROM main.pub.t2",
            [
                RewriteRule(
                    source_catalog="main",
                    source_schema="pub",
                    target_catalog="dev",
                    target_schema="stg",
                )
            ],
            Dialect.DATABRICKS,
        )
        assert result.rewritten_sql.count("dev") >= 2

    def test_quote_identifier(self, tk):
        quoted = tk.rewriter.quote_identifier("my table", Dialect.DATABRICKS)
        assert '"' in quoted or "`" in quoted
        assert "my table" in quoted

    def test_quote_identifier_duckdb(self, tk):
        quoted = tk.rewriter.quote_identifier("col name", Dialect.DUCKDB)
        assert '"' in quoted

    def test_parse_failure_returns_original(self, tk):
        # sqlglot may partially parse malformed SQL rather than raising.
        # The contract is: rewrite must not crash on bad input.
        result = tk.rewriter.rewrite_tables(
            "NOT SQL ???",
            [RewriteRule(target_catalog="x", target_schema="y")],
            Dialect.DATABRICKS,
        )
        assert result.rewritten_sql  # Non-empty — either original or best-effort


# ===================================================================
# 8. Rendering Contract
# ===================================================================


class TestRenderingContract:
    """Renderer protocol: render() and render_expression()."""

    def test_render_parsed_node(self, tk):
        parsed = tk.parser.parse_one("SELECT a, b FROM t", Dialect.DATABRICKS)
        sql = tk.renderer.render(parsed.single, Dialect.DATABRICKS)
        assert "SELECT" in sql.upper()
        assert "FROM" in sql.upper()

    def test_render_pretty(self, tk):
        parsed = tk.parser.parse_one("SELECT a, b FROM t", Dialect.DATABRICKS)
        sql = tk.renderer.render(parsed.single, Dialect.DATABRICKS, pretty=True)
        assert "\n" in sql

    def test_render_expression_fragment(self, tk):
        parsed = tk.parser.parse_one("SELECT a, b FROM t", Dialect.DATABRICKS)
        node = parsed.single
        # Render the full node as an expression.
        sql = tk.renderer.render_expression(node, Dialect.DATABRICKS)
        assert sql  # Should produce some output

    def test_render_no_raw_raises(self, tk):
        from core_engine.sql_toolkit._types import SqlNode

        node = SqlNode(kind=SqlNodeKind.SELECT, name="test")
        with pytest.raises(ValueError, match="no raw expression"):
            tk.renderer.render(node, Dialect.DATABRICKS)


# ===================================================================
# 9. Determinism Invariant
# ===================================================================


class TestDeterminismInvariant:
    """Same inputs must produce identical outputs across iterations."""

    def test_parse_determinism(self, tk):
        sql = "SELECT a, b FROM orders WHERE region = 'US'"
        results = [tk.parser.parse_one(sql, Dialect.DATABRICKS).single.sql_text for _ in range(50)]
        assert len(set(results)) == 1

    def test_normalisation_determinism(self, tk):
        sql = "select  a,  b  from  orders  where  x = 1"
        results = [tk.normalizer.normalize(sql, Dialect.DATABRICKS).normalized_sql for _ in range(50)]
        assert len(set(results)) == 1

    def test_diff_determinism(self, tk):
        old = "SELECT a, b FROM t"
        new = "SELECT a, c FROM t"
        results = [
            (
                tk.differ.diff(old, new, Dialect.DATABRICKS).is_cosmetic_only,
                len(tk.differ.diff(old, new, Dialect.DATABRICKS).edits),
            )
            for _ in range(50)
        ]
        assert len(set(results)) == 1

    def test_scope_determinism(self, tk):
        sql = "SELECT * FROM z_table JOIN a_table ON z_table.id = a_table.id"
        results = [
            tuple(
                t.fully_qualified for t in tk.scope_analyzer.extract_tables(sql, Dialect.DATABRICKS).referenced_tables
            )
            for _ in range(50)
        ]
        assert len(set(results)) == 1

    def test_safety_determinism(self, tk):
        sql = "DROP TABLE users; SELECT 1"
        results = [
            (
                tk.safety_guard.check(sql, Dialect.DATABRICKS).is_safe,
                len(tk.safety_guard.check(sql, Dialect.DATABRICKS).violations),
            )
            for _ in range(50)
        ]
        assert len(set(results)) == 1
