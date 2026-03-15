#!/usr/bin/env python3
"""
PSO RBAC - Access Control (Security Component)

Roles: admin, operator, viewer (+ custom roles)
Permissions are grouped by resource:action (e.g. services:install, tiers:write)

Usage:
    python3 -m core.rbac status
    python3 -m core.rbac role list
    python3 -m core.rbac role create devops services:install services:start services:stop
    python3 -m core.rbac user assign <username> <role>
    python3 -m core.rbac check <username> <permission>
"""

import json
import sys
from datetime import datetime
from typing import Dict, List, Optional, Set

# ─── Built-in permissions ────────────────────────────────────────────────────

ALL_PERMISSIONS = {
    # Services
    "services:list", "services:install", "services:remove",
    "services:start", "services:stop", "services:restart", "services:logs",
    # Tiers / firewall
    "tiers:read", "tiers:write",
    # Secrets
    "secrets:read", "secrets:write", "secrets:delete",
    # Updates
    "updates:read", "updates:apply",
    # Users / RBAC
    "users:read", "users:write",
    # System
    "system:backup", "system:restore", "system:config",
    # Monitoring
    "monitoring:read",
}

DEFAULT_ROLES = {
    "admin": {
        "description": "Full access to everything",
        "permissions":  list(ALL_PERMISSIONS),
        "builtin":      True,
    },
    "operator": {
        "description": "Manage services and updates, no user/secret admin",
        "permissions": [
            "services:list", "services:start", "services:stop",
            "services:restart", "services:logs", "services:install",
            "tiers:read", "updates:read", "updates:apply",
            "monitoring:read", "system:backup",
        ],
        "builtin": True,
    },
    "viewer": {
        "description": "Read-only access",
        "permissions": [
            "services:list", "services:logs", "tiers:read",
            "updates:read", "monitoring:read",
        ],
        "builtin": True,
    },
}

# ─── Schema ──────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS rbac_roles (
    name        TEXT PRIMARY KEY,
    description TEXT NOT NULL DEFAULT '',
    permissions TEXT NOT NULL DEFAULT '[]',
    builtin     INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rbac_user_roles (
    username    TEXT NOT NULL,
    role        TEXT NOT NULL,
    granted_at  TEXT NOT NULL,
    granted_by  TEXT NOT NULL DEFAULT 'system',
    PRIMARY KEY (username, role)
);
"""


def _db_conn(db_path):
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


# ─── RBAC Manager ────────────────────────────────────────────────────────────

class RBAC:

    def __init__(self, db=None):
        from core.database import Database
        self.db = db or Database()
        self._bootstrap()

    def _bootstrap(self):
        """Seed built-in roles if missing."""
        conn = _db_conn(self.db.db_path)
        for name, info in DEFAULT_ROLES.items():
            if not conn.execute("SELECT 1 FROM rbac_roles WHERE name=?", (name,)).fetchone():
                conn.execute(
                    "INSERT INTO rbac_roles (name, description, permissions, builtin, created_at) VALUES (?,?,?,?,?)",
                    (name, info["description"], json.dumps(info["permissions"]),
                     1 if info["builtin"] else 0, datetime.now().isoformat())
                )
        conn.commit()
        conn.close()

    # ── Roles ────────────────────────────────────────────────────────────────

    def list_roles(self) -> List[Dict]:
        conn = _db_conn(self.db.db_path)
        rows = conn.execute("SELECT * FROM rbac_roles ORDER BY builtin DESC, name").fetchall()
        conn.close()
        result = []
        for r in rows:
            d = dict(r)
            d["permissions"] = json.loads(d["permissions"])
            result.append(d)
        return result

    def create_role(self, name: str, description: str, permissions: List[str]) -> bool:
        unknown = set(permissions) - ALL_PERMISSIONS
        if unknown:
            raise ValueError(f"Unknown permissions: {', '.join(sorted(unknown))}")
        conn = _db_conn(self.db.db_path)
        try:
            conn.execute(
                "INSERT INTO rbac_roles (name, description, permissions, builtin, created_at) VALUES (?,?,?,0,?)",
                (name, description, json.dumps(permissions), datetime.now().isoformat())
            )
            conn.commit()
            return True
        except Exception:
            return False
        finally:
            conn.close()

    def delete_role(self, name: str) -> bool:
        conn = _db_conn(self.db.db_path)
        row = conn.execute("SELECT builtin FROM rbac_roles WHERE name=?", (name,)).fetchone()
        if not row:
            conn.close(); return False
        if row["builtin"]:
            conn.close(); raise ValueError(f"Cannot delete built-in role '{name}'")
        conn.execute("DELETE FROM rbac_roles WHERE name=?", (name,))
        conn.execute("DELETE FROM rbac_user_roles WHERE role=?", (name,))
        conn.commit(); conn.close()
        return True

    def get_permissions(self, role: str) -> Set[str]:
        conn = _db_conn(self.db.db_path)
        row = conn.execute("SELECT permissions FROM rbac_roles WHERE name=?", (role,)).fetchone()
        conn.close()
        return set(json.loads(row["permissions"])) if row else set()

    # ── Users ────────────────────────────────────────────────────────────────

    def assign_role(self, username: str, role: str, granted_by: str = "admin") -> bool:
        conn = _db_conn(self.db.db_path)
        if not conn.execute("SELECT 1 FROM rbac_roles WHERE name=?", (role,)).fetchone():
            conn.close(); raise ValueError(f"Role '{role}' does not exist")
        try:
            conn.execute(
                "INSERT OR REPLACE INTO rbac_user_roles (username, role, granted_at, granted_by) VALUES (?,?,?,?)",
                (username, role, datetime.now().isoformat(), granted_by)
            )
            conn.commit(); return True
        finally:
            conn.close()

    def revoke_role(self, username: str, role: str) -> bool:
        conn = _db_conn(self.db.db_path)
        n = conn.execute("DELETE FROM rbac_user_roles WHERE username=? AND role=?",
                         (username, role)).rowcount
        conn.commit(); conn.close()
        return n > 0

    def get_user_roles(self, username: str) -> List[str]:
        conn = _db_conn(self.db.db_path)
        rows = conn.execute("SELECT role FROM rbac_user_roles WHERE username=?", (username,)).fetchall()
        conn.close()
        return [r["role"] for r in rows]

    def get_user_permissions(self, username: str) -> Set[str]:
        perms: Set[str] = set()
        for role in self.get_user_roles(username):
            perms |= self.get_permissions(role)
        return perms

    def check(self, username: str, permission: str) -> bool:
        return permission in self.get_user_permissions(username)

    def list_users(self) -> List[Dict]:
        conn = _db_conn(self.db.db_path)
        rows = conn.execute(
            "SELECT username, GROUP_CONCAT(role) as roles FROM rbac_user_roles GROUP BY username"
        ).fetchall()
        conn.close()
        return [{"username": r["username"], "roles": r["roles"].split(",") if r["roles"] else []}
                for r in rows]


# ─── Module-level convenience ────────────────────────────────────────────────

_rbac: Optional[RBAC] = None

def check_permission(username: str, permission: str) -> bool:
    """One-line permission check from anywhere in PSO."""
    global _rbac
    if _rbac is None:
        _rbac = RBAC()
    return _rbac.check(username, permission)


# ─── CLI ─────────────────────────────────────────────────────────────────────

BOLD  = "\033[1m"; CYAN = "\033[1;36m"; GREEN = "\033[0;32m"
RED   = "\033[0;31m"; DIM = "\033[2m"; RESET = "\033[0m"


def cmd_status(_):
    rb = RBAC()
    roles = rb.list_roles()
    users = rb.list_users()
    print(f"\n  {BOLD}RBAC Status{RESET}")
    print(f"  Roles: {len(roles)}   Users with roles: {len(users)}")
    print(f"\n  {CYAN}Roles:{RESET}")
    for r in roles:
        tag = f"{DIM}[built-in]{RESET}" if r["builtin"] else ""
        print(f"    {BOLD}{r['name']:<16}{RESET} {len(r['permissions'])} perms  {DIM}{r['description']}{RESET} {tag}")
    if users:
        print(f"\n  {CYAN}Assigned users:{RESET}")
        for u in users:
            print(f"    {u['username']:<20} → {', '.join(u['roles'])}")
    print()


def cmd_role(args):
    rb = RBAC()
    sub = args[0] if args else "list"
    if sub == "list":
        cmd_status([])
    elif sub == "create":
        if len(args) < 3:
            print("\n  Usage: pso rbac role create <name> <perm1> [perm2 ...]\n"); return
        name = args[1]; perms = args[2:]
        try:
            rb.create_role(name, f"Custom role: {name}", perms)
            print(f"\n  {GREEN}✓{RESET} Role '{name}' created with {len(perms)} permissions\n")
        except ValueError as e:
            print(f"\n  {RED}✗{RESET} {e}\n")
    elif sub == "delete":
        if len(args) < 2:
            print("\n  Usage: pso rbac role delete <name>\n"); return
        try:
            rb.delete_role(args[1])
            print(f"\n  {GREEN}✓{RESET} Role '{args[1]}' deleted\n")
        except ValueError as e:
            print(f"\n  {RED}✗{RESET} {e}\n")
    elif sub == "perms":
        print(f"\n  {BOLD}All available permissions:{RESET}")
        by_resource: Dict[str, List[str]] = {}
        for p in sorted(ALL_PERMISSIONS):
            r, a = p.split(":")
            by_resource.setdefault(r, []).append(a)
        for res, actions in sorted(by_resource.items()):
            print(f"  {CYAN}{res}{RESET}  {DIM}{', '.join(actions)}{RESET}")
        print()


def cmd_user(args):
    rb = RBAC()
    sub = args[0] if args else "list"
    if sub == "assign":
        if len(args) < 3:
            print("\n  Usage: pso rbac user assign <username> <role>\n"); return
        try:
            rb.assign_role(args[1], args[2])
            print(f"\n  {GREEN}✓{RESET} {args[1]} → role '{args[2]}'\n")
        except ValueError as e:
            print(f"\n  {RED}✗{RESET} {e}\n")
    elif sub == "revoke":
        if len(args) < 3:
            print("\n  Usage: pso rbac user revoke <username> <role>\n"); return
        ok = rb.revoke_role(args[1], args[2])
        print(f"\n  {'✓ Revoked' if ok else '✗ Not found'}\n")
    elif sub == "list":
        users = rb.list_users()
        if not users:
            print("\n  No users assigned to roles yet.\n"); return
        print(f"\n  {BOLD}Users{RESET}")
        for u in users:
            perms = rb.get_user_permissions(u["username"])
            print(f"  {BOLD}{u['username']:<22}{RESET} roles={','.join(u['roles'])}  perms={len(perms)}")
        print()


def cmd_check(args):
    if len(args) < 2:
        print("\n  Usage: pso rbac check <username> <permission>\n"); return
    rb = RBAC()
    ok = rb.check(args[0], args[1])
    col = GREEN if ok else RED
    sym = "✓ ALLOWED" if ok else "✗ DENIED"
    print(f"\n  {col}{sym}{RESET}  {args[0]} → {args[1]}\n")


def main():
    args = sys.argv[1:]
    cmd  = args[0] if args else "status"
    dispatch = {"status": cmd_status, "role": cmd_role, "user": cmd_user, "check": cmd_check}
    fn = dispatch.get(cmd)
    if fn:
        fn(args[1:])
    else:
        print(f"\n  Unknown: {cmd}  —  use: status | role | user | check\n")

if __name__ == "__main__":
    main()