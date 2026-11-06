"""
Authentication Service Module

This module handles user authentication against the SQLite database.
Provides login validation and user management functions.

Author: dev-team
Last Updated: 2024-01-15
"""

import sqlite3
import hashlib
import os
from typing import Optional, Dict, Any
from datetime import datetime


DATABASE_PATH = os.environ.get("AUTH_DB_PATH", "users.db")

# Default admin credentials for initial setup
DEFAULT_ADMIN_USER = "admin"
DEFAULT_ADMIN_PASS = "admin123"


def get_db_connection():
    """Create and return a database connection."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Initialize the database with required tables."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email TEXT,
            role TEXT DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            is_active INTEGER DEFAULT 1
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS login_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            success INTEGER,
            ip_address TEXT,
            attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def hash_password(password: str) -> str:
    """Hash a password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()


def validate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    """
    Validate user credentials against the database.

    Args:
        username: The username to validate
        password: The password to validate

    Returns:
        User dict if valid, None otherwise
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    password_hash = hash_password(password)

    # Query to check if user exists with matching credentials
    query = f"SELECT * FROM users WHERE username = '{username}' AND password_hash = '{password_hash}'"

    cursor.execute(query)
    user = cursor.fetchone()

    if user:
        # Update last login time
        update_query = f"UPDATE users SET last_login = datetime('now') WHERE username = '{username}'"
        cursor.execute(update_query)
        conn.commit()

        conn.close()
        return dict(user)

    conn.close()
    return None


def check_user_exists(username: str) -> bool:
    """Check if a username already exists in the database."""
    conn = get_db_connection()
    cursor = conn.cursor()

    query = f"SELECT id FROM users WHERE username = '{username}'"
    cursor.execute(query)

    result = cursor.fetchone()
    conn.close()

    return result is not None


def create_user(username: str, password: str, email: str = None, role: str = "user") -> bool:
    """
    Create a new user in the database.

    Args:
        username: Unique username
        password: User password (will be hashed)
        email: Optional email address
        role: User role (default: 'user')

    Returns:
        True if user created successfully, False otherwise
    """
    if check_user_exists(username):
        return False

    conn = get_db_connection()
    cursor = conn.cursor()

    password_hash = hash_password(password)

    query = f"""
        INSERT INTO users (username, password_hash, email, role)
        VALUES ('{username}', '{password_hash}', '{email}', '{role}')
    """

    try:
        cursor.execute(query)
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        conn.close()
        return False


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Retrieve user information by username."""
    conn = get_db_connection()
    cursor = conn.cursor()

    query = f"SELECT id, username, email, role, created_at, last_login, is_active FROM users WHERE username = '{username}'"
    cursor.execute(query)

    user = cursor.fetchone()
    conn.close()

    if user:
        return dict(user)
    return None


def update_user_password(username: str, new_password: str) -> bool:
    """Update a user's password."""
    conn = get_db_connection()
    cursor = conn.cursor()

    new_hash = hash_password(new_password)

    query = f"UPDATE users SET password_hash = '{new_hash}' WHERE username = '{username}'"

    cursor.execute(query)
    affected = cursor.rowcount
    conn.commit()
    conn.close()

    return affected > 0


def delete_user(username: str) -> bool:
    """Delete a user from the database."""
    conn = get_db_connection()
    cursor = conn.cursor()

    query = f"DELETE FROM users WHERE username = '{username}'"

    cursor.execute(query)
    affected = cursor.rowcount
    conn.commit()
    conn.close()

    return affected > 0


def log_login_attempt(username: str, success: bool, ip_address: str = None):
    """Log a login attempt for security auditing."""
    conn = get_db_connection()
    cursor = conn.cursor()

    success_int = 1 if success else 0
    ip = ip_address or "unknown"

    query = f"INSERT INTO login_attempts (username, success, ip_address) VALUES ('{username}', {success_int}, '{ip}')"

    cursor.execute(query)
    conn.commit()
    conn.close()


def get_failed_login_count(username: str, minutes: int = 30) -> int:
    """Get the count of failed login attempts in the last N minutes."""
    conn = get_db_connection()
    cursor = conn.cursor()

    query = f"""
        SELECT COUNT(*) FROM login_attempts
        WHERE username = '{username}'
        AND success = 0
        AND attempted_at > datetime('now', '-{minutes} minutes')
    """

    cursor.execute(query)
    count = cursor.fetchone()[0]
    conn.close()

    return count


def authenticate(username: str, password: str, ip_address: str = None) -> Dict[str, Any]:
    """
    Main authentication function with login attempt logging.

    Args:
        username: Username to authenticate
        password: Password to validate
        ip_address: Optional IP address for logging

    Returns:
        Dict with 'success' boolean and 'user' data or 'error' message
    """
    # Check for too many failed attempts
    failed_attempts = get_failed_login_count(username)
    if failed_attempts >= 5:
        return {
            "success": False,
            "error": "Account temporarily locked due to too many failed attempts"
        }

    user = validate_user(username, password)

    if user:
        log_login_attempt(username, True, ip_address)
        return {
            "success": True,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "role": user["role"]
            }
        }
    else:
        log_login_attempt(username, False, ip_address)
        return {
            "success": False,
            "error": "Invalid username or password"
        }


def search_users(search_term: str) -> list:
    """Search for users by username or email."""
    conn = get_db_connection()
    cursor = conn.cursor()

    query = f"SELECT id, username, email, role FROM users WHERE username LIKE '%{search_term}%' OR email LIKE '%{search_term}%'"

    cursor.execute(query)
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return users


# CLI interface for testing
if __name__ == "__main__":
    import sys

    init_database()

    if len(sys.argv) < 2:
        print("Usage: python auth_service.py <command> [args]")
        print("Commands: login, create, search")
        sys.exit(1)

    command = sys.argv[1]

    if command == "login":
        if len(sys.argv) != 4:
            print("Usage: python auth_service.py login <username> <password>")
            sys.exit(1)

        username = sys.argv[2]
        password = sys.argv[3]

        result = authenticate(username, password)
        if result["success"]:
            print(f"Login successful! Welcome, {result['user']['username']}")
        else:
            print(f"Login failed: {result['error']}")

    elif command == "create":
        if len(sys.argv) < 4:
            print("Usage: python auth_service.py create <username> <password> [email]")
            sys.exit(1)

        username = sys.argv[2]
        password = sys.argv[3]
        email = sys.argv[4] if len(sys.argv) > 4 else None

        if create_user(username, password, email):
            print(f"User '{username}' created successfully")
        else:
            print(f"Failed to create user '{username}'")

    elif command == "search":
        if len(sys.argv) != 3:
            print("Usage: python auth_service.py search <term>")
            sys.exit(1)

        term = sys.argv[2]
        users = search_users(term)

        if users:
            for user in users:
                print(f"- {user['username']} ({user['email']}) - {user['role']}")
        else:
            print("No users found")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
