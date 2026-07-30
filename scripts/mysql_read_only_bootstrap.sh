#!/bin/sh
set -eu

valid_identifier() {
  value=$1
  case "$value" in
    ""|*[!A-Za-z0-9_]*) return 1 ;;
  esac
  [ "${#value}" -le 64 ]
}

valid_identifier "$MYSQL_DATABASE" || exit 2
valid_identifier "$MYSQL_USER" || exit 2

escaped_password=$(printf '%s' "$MYSQL_PASSWORD" | sed "s/'/''/g")

MYSQL_PWD=$MYSQL_ROOT_PASSWORD mysql \
  --host=mysql \
  --user=root \
  --batch --skip-column-names --silent <<SQL
SET SESSION sql_mode = 'NO_BACKSLASH_ESCAPES';
CREATE USER IF NOT EXISTS \`$MYSQL_USER\`@'%' IDENTIFIED BY '$escaped_password';
ALTER USER \`$MYSQL_USER\`@'%' IDENTIFIED BY '$escaped_password';
REVOKE ALL PRIVILEGES, GRANT OPTION FROM \`$MYSQL_USER\`@'%';
GRANT SELECT ON \`$MYSQL_DATABASE\`.* TO \`$MYSQL_USER\`@'%';
SQL
