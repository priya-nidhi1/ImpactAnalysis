"""Column-level SQL lineage tests (the deterministic core for SQL impact)."""

from impact.extract.sql_lineage import referenced_columns

SCHEMA = {
    "insurance.policy.policies": [
        "policy_id", "policy_status", "customer_id",
        "premium_amount", "effective_date", "expiry_date",
    ],
    "insurance.policy.claims": ["claim_id", "policy_id", "claim_amount", "claim_status"],
}


def _refs(sql):
    return referenced_columns(sql, "databricks", "insurance", "policy", SCHEMA)


def test_simple_select_with_filter():
    cols = _refs(
        "SELECT policy_id, policy_status, premium_amount "
        "FROM insurance.policy.policies WHERE policy_status = 'ACTIVE'"
    )
    assert "insurance.policy.policies.policy_status" in cols
    assert "insurance.policy.policies.premium_amount" in cols
    assert "insurance.policy.policies.policy_id" in cols


def test_join_with_aliases():
    cols = _refs(
        "SELECT p.policy_id, p.policy_status, COUNT(c.claim_id) AS claim_count "
        "FROM insurance.policy.policies p "
        "LEFT JOIN insurance.policy.claims c ON p.policy_id = c.policy_id "
        "GROUP BY p.policy_id, p.policy_status"
    )
    assert "insurance.policy.policies.policy_status" in cols
    assert "insurance.policy.claims.claim_id" in cols
    assert "insurance.policy.claims.policy_id" in cols


def test_unqualified_single_table():
    cols = _refs(
        "SELECT policy_status, COUNT(*) AS policy_count "
        "FROM insurance.policy.policies GROUP BY policy_status"
    )
    assert "insurance.policy.policies.policy_status" in cols


def test_function_wrapped_column():
    cols = _refs(
        "SELECT date_trunc('month', effective_date) AS m, SUM(premium_amount) AS t "
        "FROM insurance.policy.policies GROUP BY 1"
    )
    assert "insurance.policy.policies.effective_date" in cols
    assert "insurance.policy.policies.premium_amount" in cols
