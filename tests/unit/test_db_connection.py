from dataclasses import dataclass
import threading
import time

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

    assert manager.create_pool() is None
    assert manager.state == "ready"
    assert cursor.executed == ["SELECT CURRENT_USER()", "SHOW GRANTS FOR CURRENT_USER()"]
    assert cursor.close_count == direct.close_count == 1
    assert len(pools) == 1
    assert pools[0].kwargs["pool_size"] == 5
    assert manager.create_pool() is None
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

    assert result.code == "privilege_contract_invalid"
    assert result.message == "Database connection failed the read-only privilege check."
    assert SENTINEL not in result.message
    assert manager.state == "failed"
    assert pools == []
    assert cursor.close_count == direct.close_count == 1
    assert manager.create_pool() is result
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
    projection = manager.create_pool()
    assert projection.code == "configuration_missing"
    assert manager.get_connection() is projection


def test_concurrent_first_call_constructs_exactly_one_pool(monkeypatch):
    manager, _, _, pools = manager_with(monkeypatch)
    entered = threading.Event()
    release = threading.Event()
    original = manager._attest_read_only_principal

    def blocked_attestation():
        entered.set()
        assert release.wait(timeout=2)
        original()

    manager._attest_read_only_principal = blocked_attestation
    results = []
    threads = [threading.Thread(target=lambda: results.append(manager.create_pool())) for _ in range(2)]
    for thread in threads:
        thread.start()
    assert entered.wait(timeout=2)
    time.sleep(0.05)
    release.set()
    for thread in threads:
        thread.join(timeout=2)

    assert not any(thread.is_alive() for thread in threads)
    assert results == [None, None]
    assert len(pools) == 1


def test_concurrent_first_call_shares_one_failure(monkeypatch):
    failure = RuntimeError(SENTINEL)
    manager, _, _, pools = manager_with(monkeypatch, failure=failure)
    entered = threading.Event()
    release = threading.Event()
    original = manager._attest_read_only_principal

    def blocked_attestation():
        entered.set()
        assert release.wait(timeout=2)
        original()

    manager._attest_read_only_principal = blocked_attestation
    results = []
    threads = [threading.Thread(target=lambda: results.append(manager.create_pool())) for _ in range(2)]
    for thread in threads:
        thread.start()
    assert entered.wait(timeout=2)
    time.sleep(0.05)
    release.set()
    for thread in threads:
        thread.join(timeout=2)

    assert not any(thread.is_alive() for thread in threads)
    assert len(results) == 2
    assert results[0] is results[1]
    assert results[0].code == "execution_failed"
    assert SENTINEL not in results[0].message
    assert len(pools) == 0
