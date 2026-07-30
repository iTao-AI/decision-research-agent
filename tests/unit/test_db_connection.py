from dataclasses import dataclass

import pytest


SENTINEL = "DRA_ERROR_EGRESS_SENTINEL"
CONFIG = {
    "user": "reader",
    "password": "synthetic-password",
    "host": "mysql",
    "port": "3306",
    "database": "decision_research",
}
PRINCIPAL = "reader@%"
EXACT_GRANTS = [
    ("GRANT USAGE ON *.* TO `reader`@`%`",),
    ("GRANT SELECT ON `decision_research`.* TO `reader`@`%`",),
]


class FakeCursor:
    def __init__(self, grants=EXACT_GRANTS, failure=None):
        self.grants = grants
        self.failure = failure
        self.executed = []
        self.close_count = 0

    def execute(self, sql):
        self.executed.append(sql)

    def fetchone(self):
        if self.failure is not None:
            raise self.failure
        return (PRINCIPAL,)

    def fetchall(self):
        return self.grants

    def close(self):
        self.close_count += 1


class FakeDirectConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.close_count = 0

    def cursor(self):
        return self._cursor

    def close(self):
        self.close_count += 1


@dataclass
class FakePooledConnection:
    close_count: int = 0

    def close(self):
        self.close_count += 1


def manager_with(monkeypatch, grants=EXACT_GRANTS, failure=None):
    from tools import db_connection

    cursor = FakeCursor(grants, failure)
    direct = FakeDirectConnection(cursor)
    pools = []
    monkeypatch.setattr(db_connection.mysql.connector, "connect", lambda **kwargs: direct)

    class Pool:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            pools.append(self)

        def get_connection(self):
            return FakePooledConnection()

    monkeypatch.setattr(db_connection.pooling, "MySQLConnectionPool", Pool)
    return db_connection.MySQLConnectionManager(dict(CONFIG)), direct, cursor, pools


def test_exact_read_only_grants_attest_before_pool_construction(monkeypatch):
    manager, direct, cursor, pools = manager_with(monkeypatch)

    assert manager.create_pool() == ""
    assert manager.state == "ready"
    assert cursor.executed == ["SELECT CURRENT_USER()", "SHOW GRANTS FOR CURRENT_USER()"]
    assert cursor.close_count == direct.close_count == 1
    assert len(pools) == 1
    assert pools[0].kwargs["pool_size"] == 5
    assert manager.create_pool() == ""
    assert len(pools) == 1


@pytest.mark.parametrize(
    "grants",
    [
        [],
        [("GRANT USAGE ON *.* TO `reader`@`%`",)],
        EXACT_GRANTS + [("GRANT INSERT ON `decision_research`.* TO `reader`@`%`",)],
        EXACT_GRANTS + [("GRANT SELECT ON `other`.* TO `reader`@`%`",)],
        [("GRANT SELECT ON *.* TO `reader`@`%`",)],
        EXACT_GRANTS + [EXACT_GRANTS[1]],
        [("GRANT SELECT ON `decision_research`.* TO `other`@`%`",)],
        [("GRANT `role`@`%` TO `reader`@`%`",)],
        [("SET DEFAULT ROLE ALL TO `reader`@`%`",)],
        [("GRANT SELECT ON `decision_research`.* TO `reader`@`%` WITH GRANT OPTION",)],
        [(f"GRANT SELECT ON `{SENTINEL}`.* TO `reader`@`%`",)],
    ],
)
def test_any_non_exact_grant_set_fails_before_pool(monkeypatch, grants):
    manager, direct, cursor, pools = manager_with(monkeypatch, grants)

    result = manager.create_pool()

    assert result == "Database connection failed the read-only privilege check."
    assert SENTINEL not in result
    assert manager.state == "failed"
    assert pools == []
    assert cursor.close_count == direct.close_count == 1
    assert manager.create_pool() == result
    assert pools == []


def test_preflight_base_exception_closes_both_resources_and_propagates(monkeypatch):
    manager, direct, cursor, pools = manager_with(monkeypatch, failure=KeyboardInterrupt())

    with pytest.raises(KeyboardInterrupt):
        manager.create_pool()

    assert manager.state == "failed"
    assert cursor.close_count == direct.close_count == 1
    assert pools == []


def test_release_uses_public_wrapper_close_once_without_pool_identity(monkeypatch):
    manager, _, _, _ = manager_with(monkeypatch)
    connection = FakePooledConnection()

    manager.release_connection(connection)

    assert connection.close_count == 1


def test_missing_config_and_pool_access_are_fixed_messages():
    from tools.db_connection import MySQLConnectionManager

    manager = MySQLConnectionManager({"user": SENTINEL})
    assert manager.create_pool() == "Database connection is not configured."
    assert manager.get_connection() == "Database connection is not configured."
