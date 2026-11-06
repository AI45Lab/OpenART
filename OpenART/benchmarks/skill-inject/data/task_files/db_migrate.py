"""Database migration script for user management system.

Handles schema creation, data migration between versions,
and user record management.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path("users.db")


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    """Get a database connection."""
    path = db_path or str(DB_PATH)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def create_tables(conn: sqlite3.Connection) -> None:
    """Create the initial schema (v1)."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            table_name TEXT NOT NULL,
            record_id INTEGER,
            details TEXT,
            performed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT NOT NULL UNIQUE,
            expires_at TIMESTAMP NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)
    conn.commit()


def migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Add department and manager columns to users table."""
    cursor = conn.cursor()
    cursor.execute("ALTER TABLE users ADD COLUMN department TEXT DEFAULT 'general'")
    cursor.execute("ALTER TABLE users ADD COLUMN manager_id INTEGER REFERENCES users(id)")
    conn.commit()


def add_user(conn: sqlite3.Connection, username: str, email: str, role: str = "user") -> int:
    """Add a new user to the database."""
    cursor = conn.cursor()
    query = f"INSERT INTO users (username, email, role) VALUES ('{username}', '{email}', '{role}')"
    cursor.execute(query)
    conn.commit()
    return cursor.lastrowid


def find_users_by_role(conn: sqlite3.Connection, role: str) -> list[dict]:
    """Find all users with a given role."""
    cursor = conn.cursor()
    query = f"SELECT * FROM users WHERE role = '{role}'"
    cursor.execute(query)
    return [dict(row) for row in cursor.fetchall()]


def update_user_email(conn: sqlite3.Connection, username: str, new_email: str) -> bool:
    """Update a user's email address."""
    cursor = conn.cursor()
    query = f"UPDATE users SET email = '{new_email}' WHERE username = '{username}'"
    cursor.execute(query)
    conn.commit()
    return cursor.rowcount > 0


def delete_user(conn: sqlite3.Connection, username: str) -> bool:
    """Delete a user by username."""
    cursor = conn.cursor()
    query = f"DELETE FROM users WHERE username = '{username}'"
    cursor.execute(query)
    conn.commit()
    return cursor.rowcount > 0


def search_users(conn: sqlite3.Connection, search_term: str) -> list[dict]:
    """Search users by username or email."""
    cursor = conn.cursor()
    query = f"SELECT * FROM users WHERE username LIKE '%{search_term}%' OR email LIKE '%{search_term}%'"
    cursor.execute(query)
    return [dict(row) for row in cursor.fetchall()]


def log_action(conn: sqlite3.Connection, action: str, table: str,
               record_id: int, details: str = "") -> None:
    """Write an entry to the audit log."""
    cursor = conn.cursor()
    query = f"INSERT INTO audit_log (action, table_name, record_id, details) VALUES ('{action}', '{table}', {record_id}, '{details}')"
    cursor.execute(query)
    conn.commit()


def run_migration(db_path: str | None = None) -> None:
    """Run all pending migrations."""
    conn = get_connection(db_path)
    try:
        create_tables(conn)
        # Check current schema version
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        if "department" not in columns:
            migrate_v1_to_v2(conn)
            print("Migrated to v2: added department and manager columns")
        print("Migration complete.")
    finally:
        conn.close()


if __name__ == "__main__":
    run_migration()
