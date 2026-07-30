"""MySQL read-only principal attestation and connector pool lifecycle."""

from __future__ import annotations

import re
from threading import Condition

import mysql.connector
from mysql.connector import Error, pooling

from tools.error_projection import ErrorProjection, classify_exception, projection_for


class PrivilegeContractError(RuntimeError):
    """The observed principal grants are not exactly schema SELECT-only."""


class MySQLConnectionManager:
    """Create a pool only after a direct read-only grant attestation."""

    def __init__(self, config: dict):
        self.config = config
        self._pool = None
        self.state = "uninitialized"
        self._failure_projection: ErrorProjection | None = None
        self._condition = Condition()

    def _required_config_present(self) -> bool:
        return all(self.config.get(key) for key in ("user", "password", "host", "port", "database"))

    def _attest_read_only_principal(self) -> None:
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(**self.config)
            cursor = connection.cursor()
            cursor.execute("SELECT CURRENT_USER()")
            principal_row = cursor.fetchone()
            cursor.execute("SHOW GRANTS FOR CURRENT_USER()")
            grant_rows = cursor.fetchall()
            self._validate_grants(principal_row, grant_rows)
        finally:
            try:
                if cursor is not None:
                    cursor.close()
            finally:
                if connection is not None:
                    connection.close()

    def _validate_grants(self, principal_row, grant_rows) -> None:
        if not isinstance(principal_row, (tuple, list)) or len(principal_row) != 1:
            raise PrivilegeContractError("principal shape")
        principal = principal_row[0]
        if not isinstance(principal, str) or principal.count("@") != 1:
            raise PrivilegeContractError("principal shape")
        user, host = principal.split("@", 1)
        database = self.config.get("database")
        identifier = re.compile(r"^[A-Za-z0-9_]{1,64}$")
        if not identifier.fullmatch(user) or not identifier.fullmatch(database or ""):
            raise PrivilegeContractError("principal shape")
        if not host or "`" in host:
            raise PrivilegeContractError("principal shape")
        quoted_principal = f"`{user}`@`{host}`"
        allowed = {
            f"GRANT USAGE ON *.* TO {quoted_principal}",
            f"GRANT SELECT ON `{database}`.* TO {quoted_principal}",
        }
        observed: list[str] = []
        for row in grant_rows:
            if not isinstance(row, (tuple, list)) or len(row) != 1 or not isinstance(row[0], str):
                raise PrivilegeContractError("grant shape")
            observed.append(row[0])
        if len(observed) != len(set(observed)):
            raise PrivilegeContractError("duplicate grant")
        required_select = f"GRANT SELECT ON `{database}`.* TO {quoted_principal}"
        if required_select not in observed or not set(observed).issubset(allowed):
            raise PrivilegeContractError("grant set")

    def configure_and_create_pool(self, config: dict) -> ErrorProjection | None:
        with self._condition:
            if self.state == "uninitialized":
                self.config = config
        return self.create_pool()

    def create_pool(self) -> ErrorProjection | None:
        with self._condition:
            while self.state == "attesting":
                self._condition.wait()
            if self.state == "ready":
                return None
            if self.state == "failed":
                return self._failure_projection or projection_for(
                    operation="mysql_connect", code="execution_failed"
                )
            if not self._required_config_present():
                self.state = "failed"
                self._failure_projection = projection_for(
                    operation="mysql_connect", code="configuration_missing"
                )
                self._condition.notify_all()
                return self._failure_projection
            self.state = "attesting"
        try:
            self._attest_read_only_principal()
            pool = pooling.MySQLConnectionPool(
                pool_name="decision_research_pool",
                pool_size=5,
                pool_reset_session=True,
                connection_timeout=10,
                **self.config,
            )
        except PrivilegeContractError:
            projection = projection_for(
                operation="mysql_connect", code="privilege_contract_invalid"
            )
        except BaseException as exc:
            if not isinstance(exc, Exception):
                with self._condition:
                    self.state = "failed"
                    self._condition.notify_all()
                raise
            projection = classify_exception(exc, operation="mysql_connect")
        else:
            with self._condition:
                self._pool = pool
                self.state = "ready"
                self._condition.notify_all()
            return None
        with self._condition:
            self.state = "failed"
            self._failure_projection = projection
            self._condition.notify_all()
        return projection

    def get_connection(self):
        if self._pool is None:
            if self._failure_projection is not None:
                return self._failure_projection
            return projection_for(operation="mysql_connect", code="configuration_missing")
        try:
            return self._pool.get_connection()
        except Exception as exc:
            return classify_exception(exc, operation="mysql_connect")

    def release_connection(self, connection) -> None:
        if connection is not None:
            connection.close()
