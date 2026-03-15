#!/usr/bin/env python3
"""
PSO Secrets Manager
Manages encrypted secrets and credentials for services
"""

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict
from base64 import b64encode, b64decode
from cryptography.fernet import Fernet


# Get database path from environment or use default
DB_PATH = Path(os.getenv("PSO_DB_PATH", str(Path.home() / ".pso" / "pso.db")))


class SecretsManagerError(Exception):
    """Base exception for secrets manager errors"""
    pass


def _get_encryption_key() -> bytes:
    """
    Get or create encryption key for secrets.

    In a production environment, this should be stored securely
    (e.g., in a key management service or hardware security module).
    For now, we store it in the PSO directory.
    """
    key_file = DB_PATH.parent / ".secrets_key"

    if key_file.exists():
        with open(key_file, 'rb') as f:
            return f.read()
    else:
        # Generate new key
        key = Fernet.generate_key()
        key_file.parent.mkdir(parents=True, exist_ok=True)
        with open(key_file, 'wb') as f:
            f.write(key)
        # Restrict permissions (owner read/write only)
        os.chmod(key_file, 0o600)
        return key


class SecretsManager:
    """
    Manages encrypted secrets and credentials for services

    Handles:
    - Storing encrypted secrets
    - Retrieving and decrypting secrets
    - Listing available secrets
    - Deleting secrets
    """

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize secrets manager

        Args:
            db_path: Database path (uses global DB_PATH if not provided)
        """
        self.db_path = db_path or DB_PATH
        self._ensure_schema()

        # Initialize encryption
        try:
            key = _get_encryption_key()
            self.cipher = Fernet(key)
        except Exception as e:
            raise SecretsManagerError(f"Failed to initialize encryption: {e}")

    def _ensure_schema(self):
        """Ensure secrets table exists"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS secrets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    value_enc TEXT,
                    service_id TEXT,
                    description TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            raise SecretsManagerError(f"Failed to initialize schema: {e}")

    def _encrypt(self, value: str) -> str:
        """Encrypt a secret value"""
        try:
            encrypted = self.cipher.encrypt(value.encode())
            return b64encode(encrypted).decode()
        except Exception as e:
            raise SecretsManagerError(f"Encryption failed: {e}")

    def _decrypt(self, encrypted_value: str) -> str:
        """Decrypt a secret value"""
        try:
            decoded = b64decode(encrypted_value.encode())
            decrypted = self.cipher.decrypt(decoded)
            return decrypted.decode()
        except Exception as e:
            raise SecretsManagerError(f"Decryption failed: {e}")

    def set(self, name: str, value: str, service_id: Optional[str] = None,
            description: Optional[str] = None) -> bool:
        """
        Store a secret

        Args:
            name: Secret identifier
            value: Secret value (will be encrypted)
            service_id: Optional service this secret belongs to
            description: Optional description

        Returns:
            True if successful

        Raises:
            SecretsManagerError: If storage fails
        """
        try:
            encrypted_value = self._encrypt(value)
            now = datetime.now().isoformat()

            conn = sqlite3.connect(self.db_path)

            # Check if secret already exists
            cursor = conn.execute(
                "SELECT id FROM secrets WHERE name = ?",
                (name,)
            )
            existing = cursor.fetchone()

            if existing:
                # Update existing secret
                conn.execute("""
                    UPDATE secrets
                    SET value_enc = ?, service_id = ?, description = ?, updated_at = ?
                    WHERE name = ?
                """, (encrypted_value, service_id, description, now, name))
            else:
                # Insert new secret
                conn.execute("""
                    INSERT INTO secrets (name, value_enc, service_id, description, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (name, encrypted_value, service_id, description, now, now))

            conn.commit()
            conn.close()
            return True

        except sqlite3.Error as e:
            raise SecretsManagerError(f"Failed to store secret: {e}")

    def get(self, name: str) -> Optional[str]:
        """
        Retrieve a secret

        Args:
            name: Secret identifier

        Returns:
            Decrypted secret value, or None if not found

        Raises:
            SecretsManagerError: If retrieval or decryption fails
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute(
                "SELECT value_enc FROM secrets WHERE name = ?",
                (name,)
            )
            row = cursor.fetchone()
            conn.close()

            if not row or not row[0]:
                return None

            return self._decrypt(row[0])

        except sqlite3.Error as e:
            raise SecretsManagerError(f"Failed to retrieve secret: {e}")

    def get_secret(self, name: str) -> Optional[str]:
        """
        Alias for get() - retrieve a secret

        Args:
            name: Secret identifier

        Returns:
            Decrypted secret value, or None if not found
        """
        return self.get(name)

    def list(self, service_id: Optional[str] = None) -> List[Dict[str, any]]:
        """
        List all secrets (metadata only, not values)

        Args:
            service_id: Optional filter by service

        Returns:
            List of secret metadata dictionaries
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row

            if service_id:
                cursor = conn.execute(
                    """SELECT id, name, service_id, description, created_at, updated_at
                       FROM secrets WHERE service_id = ?""",
                    (service_id,)
                )
            else:
                cursor = conn.execute(
                    "SELECT id, name, service_id, description, created_at, updated_at FROM secrets"
                )

            secrets = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return secrets

        except sqlite3.Error as e:
            raise SecretsManagerError(f"Failed to list secrets: {e}")

    def delete(self, name: str) -> bool:
        """
        Delete a secret

        Args:
            name: Secret identifier

        Returns:
            True if deleted, False if not found

        Raises:
            SecretsManagerError: If deletion fails
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute(
                "DELETE FROM secrets WHERE name = ?",
                (name,)
            )
            deleted = cursor.rowcount > 0
            conn.commit()
            conn.close()
            return deleted

        except sqlite3.Error as e:
            raise SecretsManagerError(f"Failed to delete secret: {e}")

    def delete_service_secrets(self, service_id: str) -> int:
        """
        Delete all secrets for a service

        Args:
            service_id: Service identifier

        Returns:
            Number of secrets deleted
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute(
                "DELETE FROM secrets WHERE service_id = ?",
                (service_id,)
            )
            count = cursor.rowcount
            conn.commit()
            conn.close()
            return count

        except sqlite3.Error as e:
            raise SecretsManagerError(f"Failed to delete service secrets: {e}")


# Convenience functions
def get_secret(name: str) -> Optional[str]:
    """Get a secret value"""
    manager = SecretsManager()
    return manager.get(name)


def set_secret(name: str, value: str, service_id: Optional[str] = None,
               description: Optional[str] = None) -> bool:
    """Set a secret value"""
    manager = SecretsManager()
    return manager.set(name, value, service_id, description)


def delete_secret(name: str) -> bool:
    """Delete a secret"""
    manager = SecretsManager()
    return manager.delete(name)


def list_secrets(service_id: Optional[str] = None) -> List[Dict]:
    """List all secrets"""
    manager = SecretsManager()
    return manager.list(service_id)


if __name__ == '__main__':
    import sys

    # Simple CLI for testing
    if len(sys.argv) < 2:
        print("Usage: python -m core.secrets_manager <command> [args]")
        print("\nCommands:")
        print("  list                      - List all secrets")
        print("  set <name> <value>        - Set a secret")
        print("  get <name>                - Get a secret")
        print("  delete <name>             - Delete a secret")
        sys.exit(1)

    command = sys.argv[1]
    manager = SecretsManager()

    try:
        if command == 'list':
            secrets = manager.list()
            if not secrets:
                print("No secrets stored")
            else:
                print(f"\n{'Name':<30} {'Service':<20} {'Created'}")
                print("─" * 70)
                for s in secrets:
                    service = s.get('service_id') or '-'
                    created = s.get('created_at', '')[:19]
                    print(f"{s['name']:<30} {service:<20} {created}")

        elif command == 'set':
            if len(sys.argv) < 4:
                print("Error: set requires <name> <value>")
                sys.exit(1)
            name, value = sys.argv[2], sys.argv[3]
            service_id = sys.argv[4] if len(sys.argv) > 4 else None
            manager.set(name, value, service_id)
            print(f"✓ Secret '{name}' stored")

        elif command == 'get':
            if len(sys.argv) < 3:
                print("Error: get requires <name>")
                sys.exit(1)
            name = sys.argv[2]
            value = manager.get(name)
            if value is None:
                print(f"Secret '{name}' not found")
            else:
                print(value)

        elif command == 'delete':
            if len(sys.argv) < 3:
                print("Error: delete requires <name>")
                sys.exit(1)
            name = sys.argv[2]
            if manager.delete(name):
                print(f"✓ Secret '{name}' deleted")
            else:
                print(f"Secret '{name}' not found")

        else:
            print(f"Unknown command: {command}")
            sys.exit(1)

    except SecretsManagerError as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)
