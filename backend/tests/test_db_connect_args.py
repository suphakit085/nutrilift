"""The engine must stay usable behind Supabase's transaction-mode pooler.

Production points ``DATABASE_URL`` at port 6543, where consecutive transactions
can land on different server connections. psycopg3's automatic prepared
statements break under that, and only after the same query has run five times -
late enough to look like a random production flake. See
``app.db.session.connect_args_for``.
"""

from app.db.session import connect_args_for

SUPABASE_POOLED = (
    "postgresql+psycopg://postgres.abcd:pw@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres"
)
LOCAL_DIRECT = "postgresql+psycopg://nutrition:nutrition@localhost:5432/nutrition"


def test_prepared_statements_disabled_on_the_pooled_endpoint() -> None:
    assert connect_args_for(SUPABASE_POOLED) == {"prepare_threshold": None}


def test_same_setting_on_a_direct_connection() -> None:
    """Deliberately not conditional on the port: the pooled host is what we
    deploy against, and a setting that only applies to one URL shape is a
    setting that silently stops applying when the URL changes."""
    assert connect_args_for(LOCAL_DIRECT) == {"prepare_threshold": None}


def test_no_psycopg_args_leak_to_other_drivers() -> None:
    """``prepare_threshold`` is a psycopg keyword; passing it to another DBAPI
    would raise at connect time rather than be ignored."""
    assert connect_args_for("sqlite:///./test.db") == {}
    assert connect_args_for("postgresql+asyncpg://u:p@localhost/db") == {}
