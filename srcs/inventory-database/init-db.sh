#!/bin/bash
set -euo pipefail

PGDATA="${PGDATA:-/var/lib/postgresql/data}"
: "${DB_USER:?DB_USER environment variable must be set}"
: "${DB_PASSWORD:?DB_PASSWORD environment variable must be set}"
: "${DB_NAME:?DB_NAME environment variable must be set}"

mkdir -p "$PGDATA" /run/postgresql
chown -R postgres:postgres /run/postgresql

# Reconcile the application role and database against the current environment.
# Runs on every boot, not only on first initialisation, so editing a credential
# in `.env` is picked up instead of leaving a role whose password no longer
# matches (which would surface as a confusing crash-loop in the app container
# while the database container still reports itself healthy).
reconcile() {
  echo "[init-db] Reconciling role '$DB_USER' and database '$DB_NAME'..."
  su-exec postgres pg_ctl -D "$PGDATA" -w start

  # The password is delivered through a 0600 file read by `psql -f` instead of
  # `-v db_password=...`, which would expose it in /proc/<pid>/cmdline to every
  # process in the container. The file holds a `\set` line, so it must be quoted
  # for psql: single quotes are doubled and backslashes are doubled.
  local sql_file escaped_password
  sql_file="$(mktemp)"
  escaped_password="${DB_PASSWORD//\\/\\\\}"
  escaped_password="${escaped_password//\'/\'\'}"
  {
    printf "\\set db_password '%s'\n" "$escaped_password"
    echo "SELECT format('CREATE ROLE %I WITH LOGIN PASSWORD %L', :'db_user', :'db_password')"
    echo " WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'db_user') \\gexec"
    echo "SELECT format('ALTER ROLE %I WITH LOGIN PASSWORD %L', :'db_user', :'db_password')"
    echo " WHERE     EXISTS (SELECT FROM pg_roles WHERE rolname = :'db_user') \\gexec"
    echo "SELECT format('CREATE DATABASE %I OWNER %I', :'db_name', :'db_user')"
    echo " WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'db_name') \\gexec"
    echo "SELECT format('GRANT ALL PRIVILEGES ON DATABASE %I TO %I', :'db_name', :'db_user') \\gexec"
  } > "$sql_file"
  chown postgres:postgres "$sql_file"
  chmod 600 "$sql_file"

  # db_user / db_name are not secrets and stay in argv; db_password is not.
  su-exec postgres psql -U postgres -d postgres -q -v ON_ERROR_STOP=1 \
       -v db_user="$DB_USER" -v db_name="$DB_NAME" -f "$sql_file" < /dev/null
  rm -f "$sql_file"

  su-exec postgres pg_ctl -D "$PGDATA" -m fast -w stop
  echo "[init-db] Role and database are in sync with the configured credentials."
}

if [ ! -s "$PGDATA/PG_VERSION" ]; then
  echo "[init-db] Initializing new PostgreSQL database cluster in $PGDATA..."
  chown -R postgres:postgres "$PGDATA"
  chmod 700 "$PGDATA"

  su-exec postgres initdb -D "$PGDATA" -U postgres \
    --auth-host=scram-sha-256 --auth-local=trust

  # Enable listening on all interfaces and allow network authentication
  echo "listen_addresses = '*'" >> "$PGDATA/postgresql.conf"
  echo "host all all 0.0.0.0/0 scram-sha-256" >> "$PGDATA/pg_hba.conf"
  echo "host all all ::/0 scram-sha-256" >> "$PGDATA/pg_hba.conf"

  reconcile
  echo "[init-db] Database initialization completed successfully."
else
  echo "[init-db] Existing PostgreSQL database cluster detected in $PGDATA."
  if ! reconcile; then
    # Non-fatal: a failure here must not stop the server from starting and
    # serving whatever state the cluster is already in.
    echo "[init-db] WARNING: credential reconciliation failed; continuing with existing cluster state." >&2
  fi
fi

echo "[init-db] Starting PostgreSQL server..."
exec su-exec postgres postgres -D "$PGDATA" -h "*"