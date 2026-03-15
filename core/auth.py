#!/usr/bin/env python3
"""
PSO Authentication System
User management, password hashing, and session handling
"""

import jwt
import bcrypt
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple

# Bootstrap Python path for cross-package imports
from core import _bootstrap


class AuthError(Exception):
    """Base exception for authentication errors"""
    pass


class Auth:
    """
    Authentication manager for PSO
    - User registration and login
    - Password hashing with bcrypt
    - JWT-based session management
    - Token validation and refresh
    """
    
    def __init__(self, db, secret_key: Optional[str] = None, 
                 token_expiry_hours: int = 24):
        """
        Initialize authentication system
        
        Args:
            db: Database instance
            secret_key: JWT secret key (auto-generated if not provided)
            token_expiry_hours: Token expiration time in hours
        """
        self.db = db
        self.secret_key = secret_key or secrets.token_hex(32)
        self.token_expiry_hours = token_expiry_hours
        self.algorithm = 'HS256'
        
        # Initialize database tables
        self._init_db()
    
    def _init_db(self):
        """Create authentication tables"""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            
            # Users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE,
                    password_hash TEXT NOT NULL,
                    full_name TEXT,
                    is_active INTEGER DEFAULT 1,
                    is_admin INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_login DATETIME,
                    UNIQUE(username)
                )
            ''')
            
            # Sessions table (for token tracking/revocation)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    token_jti TEXT UNIQUE NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    expires_at DATETIME NOT NULL,
                    revoked INTEGER DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''')
            
            # Create default admin user if no users exist
            cursor.execute('SELECT COUNT(*) FROM users')
            if cursor.fetchone()[0] == 0:
                # Default credentials: admin / pso-admin-2026
                default_hash = self._hash_password('pso-admin-2026')
                cursor.execute('''
                    INSERT INTO users (username, email, password_hash, full_name, is_admin)
                    VALUES (?, ?, ?, ?, ?)
                ''', ('admin', 'admin@pso.local', default_hash, 'Administrator', 1))
    
    def _hash_password(self, password: str) -> str:
        """Hash password using bcrypt"""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    
    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verify password against hash"""
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
    
    def _generate_token(self, user_id: int, username: str) -> Tuple[str, str]:
        """
        Generate JWT token
        
        Returns:
            Tuple of (token, jti)
        """
        jti = secrets.token_hex(16)  # Unique token ID for revocation
        expires_at = datetime.utcnow() + timedelta(hours=self.token_expiry_hours)
        
        payload = {
            'user_id': user_id,
            'username': username,
            'jti': jti,
            'exp': expires_at,
            'iat': datetime.utcnow()
        }
        
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        return token, jti
    
    def register_user(self, username: str, password: str, 
                     email: Optional[str] = None, 
                     full_name: Optional[str] = None,
                     is_admin: bool = False) -> Dict:
        """
        Register a new user
        
        Args:
            username: Username (must be unique)
            password: Plain text password (will be hashed)
            email: Email address (optional)
            full_name: Full name (optional)
            is_admin: Admin privileges (default: False)
            
        Returns:
            User info dict
            
        Raises:
            AuthError: If username already exists or validation fails
        """
        # Validate username
        if len(username) < 3:
            raise AuthError("Username must be at least 3 characters")
        
        # Validate password
        if len(password) < 8:
            raise AuthError("Password must be at least 8 characters")
        
        # Hash password
        password_hash = self._hash_password(password)
        
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            
            try:
                cursor.execute('''
                    INSERT INTO users (username, email, password_hash, full_name, is_admin)
                    VALUES (?, ?, ?, ?, ?)
                ''', (username, email, password_hash, full_name, 1 if is_admin else 0))
                
                user_id = cursor.lastrowid
                
                return {
                    'id': user_id,
                    'username': username,
                    'email': email,
                    'full_name': full_name,
                    'is_admin': is_admin
                }
                
            except Exception as e:
                if 'UNIQUE constraint failed' in str(e):
                    raise AuthError(f"Username '{username}' already exists")
                raise AuthError(f"Registration failed: {e}")
    
    def login(self, username: str, password: str, remember_me: bool = False) -> Dict:
        """
        Authenticate user and create session
        
        Args:
            username: Username
            password: Plain text password
            remember_me: If True, token expires in 30 days instead of 24 hours
            
        Returns:
            Dict with user info and token
            
        Raises:
            AuthError: If credentials are invalid
        """
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            
            # Get user
            cursor.execute('''
                SELECT id, username, email, password_hash, full_name, is_active, is_admin
                FROM users WHERE username = ?
            ''', (username,))
            
            user = cursor.fetchone()
            
            if not user:
                raise AuthError("Invalid username or password")
            
            user_dict = dict(user)
            
            # Check if active
            if not user_dict['is_active']:
                raise AuthError("Account is disabled")
            
            # Verify password
            if not self._verify_password(password, user_dict['password_hash']):
                raise AuthError("Invalid username or password")
            
            # Generate token
            expiry_hours = 720 if remember_me else self.token_expiry_hours  # 30 days or 24 hours
            token, jti = self._generate_token(user_dict['id'], user_dict['username'])
            
            # Store session
            expires_at = datetime.utcnow() + timedelta(hours=expiry_hours)
            cursor.execute('''
                INSERT INTO sessions (user_id, token_jti, expires_at)
                VALUES (?, ?, ?)
            ''', (user_dict['id'], jti, expires_at))
            
            # Update last login
            cursor.execute('''
                UPDATE users SET last_login = ? WHERE id = ?
            ''', (datetime.utcnow(), user_dict['id']))
            
            return {
                'user': {
                    'id': user_dict['id'],
                    'username': user_dict['username'],
                    'email': user_dict['email'],
                    'full_name': user_dict['full_name'],
                    'is_admin': bool(user_dict['is_admin'])
                },
                'token': token,
                'expires_at': expires_at.isoformat()
            }
    
    def validate_token(self, token: str) -> Optional[Dict]:
        """
        Validate JWT token
        
        Args:
            token: JWT token string
            
        Returns:
            User info dict if valid, None otherwise
        """
        try:
            # Decode token
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            
            user_id = payload['user_id']
            jti = payload['jti']
            
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if session is revoked
                cursor.execute('''
                    SELECT revoked FROM sessions 
                    WHERE token_jti = ? AND user_id = ?
                ''', (jti, user_id))
                
                session = cursor.fetchone()
                if session and session['revoked']:
                    return None
                
                # Get user info
                cursor.execute('''
                    SELECT id, username, email, full_name, is_active, is_admin
                    FROM users WHERE id = ?
                ''', (user_id,))
                
                user = cursor.fetchone()
                if not user:
                    return None
                
                user_dict = dict(user)
                
                # Check if active
                if not user_dict['is_active']:
                    return None
                
                return {
                    'id': user_dict['id'],
                    'username': user_dict['username'],
                    'email': user_dict['email'],
                    'full_name': user_dict['full_name'],
                    'is_admin': bool(user_dict['is_admin'])
                }
                
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
        except Exception:
            return None
    
    def logout(self, token: str) -> bool:
        """
        Logout user by revoking token
        
        Args:
            token: JWT token to revoke
            
        Returns:
            True if successful
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            jti = payload['jti']
            
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE sessions SET revoked = 1 WHERE token_jti = ?
                ''', (jti,))
                
            return True
            
        except Exception:
            return False
    
    def change_password(self, user_id: int, old_password: str, new_password: str) -> bool:
        """
        Change user password
        
        Args:
            user_id: User ID
            old_password: Current password
            new_password: New password
            
        Returns:
            True if successful
            
        Raises:
            AuthError: If old password is incorrect or validation fails
        """
        if len(new_password) < 8:
            raise AuthError("New password must be at least 8 characters")
        
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            
            # Get current password hash
            cursor.execute('SELECT password_hash FROM users WHERE id = ?', (user_id,))
            user = cursor.fetchone()
            
            if not user:
                raise AuthError("User not found")
            
            # Verify old password
            if not self._verify_password(old_password, user['password_hash']):
                raise AuthError("Current password is incorrect")
            
            # Hash new password
            new_hash = self._hash_password(new_password)
            
            # Update password
            cursor.execute('''
                UPDATE users SET password_hash = ? WHERE id = ?
            ''', (new_hash, user_id))
            
            # Revoke all existing sessions (force re-login)
            cursor.execute('UPDATE sessions SET revoked = 1 WHERE user_id = ?', (user_id,))
            
            return True
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user info by ID"""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, username, email, full_name, is_active, is_admin, created_at, last_login
                FROM users WHERE id = ?
            ''', (user_id,))
            
            user = cursor.fetchone()
            if not user:
                return None
            
            return dict(user)
    
    def list_users(self) -> list:
        """List all users (admin only)"""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, username, email, full_name, is_active, is_admin, created_at, last_login
                FROM users
                ORDER BY username
            ''')
            
            return [dict(row) for row in cursor.fetchall()]
    
    def delete_user(self, user_id: int) -> bool:
        """Delete a user"""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
            return cursor.rowcount > 0
    
    def cleanup_expired_sessions(self):
        """Remove expired sessions from database"""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM sessions 
                WHERE expires_at < ? OR revoked = 1
            ''', (datetime.utcnow(),))
            return cursor.rowcount


# CLI Interface
if __name__ == '__main__':
    import sys
    from pathlib import Path
    
    # Add parent directory to path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    
    from core.database import Database
    
    db = Database()
    auth = Auth(db)
    
    if len(sys.argv) < 2:
        print("PSO Authentication CLI")
        print("\nCommands:")
        print("  register <username> <password> [--admin]  - Register new user")
        print("  login <username> <password>               - Test login")
        print("  list                                      - List all users")
        print("  cleanup                                   - Clean expired sessions")
        print("\nDefault admin credentials:")
        print("  Username: admin")
        print("  Password: pso-admin-2026")
        sys.exit(0)
    
    cmd = sys.argv[1]
    
    if cmd == 'register':
        if len(sys.argv) < 4:
            print("Usage: python auth.py register <username> <password> [--admin]")
            sys.exit(1)
        
        username = sys.argv[2]
        password = sys.argv[3]
        is_admin = '--admin' in sys.argv
        
        try:
            user = auth.register_user(username, password, is_admin=is_admin)
            print(f"✓ Registered user: {user['username']}")
            if is_admin:
                print("  Admin privileges granted")
        except AuthError as e:
            print(f"✗ Error: {e}")
            sys.exit(1)
    
    elif cmd == 'login':
        if len(sys.argv) < 4:
            print("Usage: python auth.py login <username> <password>")
            sys.exit(1)
        
        username = sys.argv[2]
        password = sys.argv[3]
        
        try:
            result = auth.login(username, password)
            print(f"✓ Login successful!")
            print(f"  User: {result['user']['username']}")
            print(f"  Token: {result['token'][:50]}...")
            print(f"  Expires: {result['expires_at']}")
        except AuthError as e:
            print(f"✗ Error: {e}")
            sys.exit(1)
    
    elif cmd == 'list':
        users = auth.list_users()
        print(f"\nUsers ({len(users)}):")
        print("=" * 80)
        for user in users:
            admin_badge = " [ADMIN]" if user['is_admin'] else ""
            active_badge = "" if user['is_active'] else " [DISABLED]"
            print(f"{user['username']:<20} {user['email'] or 'no email':<30}{admin_badge}{active_badge}")
    
    elif cmd == 'cleanup':
        count = auth.cleanup_expired_sessions()
        print(f"✓ Cleaned up {count} expired/revoked sessions")
    
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)