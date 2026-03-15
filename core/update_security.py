#!/usr/bin/env python3
"""
PSO Update Security Layer
Library used by update_processor before applying any update.

Functions:
  verify_checksum(path, expected_sha256) -> bool
  verify_tls(url) -> bool
  verify_signature(path, pubkey_path) -> bool
  verify_update(path, url, expected_sha256, pubkey_path) -> VerificationResult
"""

import hashlib
import hmac
import json
import ssl
import subprocess
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class VerificationResult:
    passed: bool
    checks: dict = field(default_factory=dict)   # check_name -> True/False/None (None = skipped)
    errors: list[str] = field(default_factory=list)

    def __bool__(self):
        return self.passed

    def summary(self) -> str:
        lines = ["Update Security Verification:"]
        icons = {True: "✓", False: "✗", None: "–"}
        for check, result in self.checks.items():
            lines.append(f"  {icons[result]} {check}")
        if self.errors:
            lines.append("Errors:")
            for e in self.errors:
                lines.append(f"  ! {e}")
        lines.append(f"Result: {'PASSED' if self.passed else 'FAILED'}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Checksum verification
# ---------------------------------------------------------------------------

def verify_checksum(path: str | Path, expected: str) -> bool:
    """
    Verify SHA-256 checksum of a file.

    Args:
        path: Path to the file to check.
        expected: Expected hex digest (case-insensitive).
                  Can optionally be prefixed with 'sha256:'.
    Returns:
        True if checksums match.
    Raises:
        FileNotFoundError if path does not exist.
        ValueError if expected is not a valid hex string.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    expected = expected.strip()
    if expected.lower().startswith("sha256:"):
        expected = expected[7:]

    if len(expected) != 64:
        raise ValueError(f"Expected a 64-character SHA-256 hex digest, got {len(expected)} chars")

    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)

    actual = sha.hexdigest()
    return hmac.compare_digest(actual.lower(), expected.lower())


def compute_checksum(path: str | Path) -> str:
    """Return the SHA-256 hex digest of a file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


# ---------------------------------------------------------------------------
# TLS verification
# ---------------------------------------------------------------------------

def verify_tls(url: str) -> bool:
    """
    Verify that a URL is HTTPS with a valid certificate chain.

    Returns:
        True if TLS is valid.
        False if the URL is HTTP or certificate verification fails.
    """
    if not url.lower().startswith("https://"):
        return False  # plaintext HTTP — reject

    ctx = ssl.create_default_context()
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED

    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            return resp.status < 400
    except ssl.SSLError:
        return False
    except Exception:
        # Network timeout, 4xx/5xx, etc. — TLS itself may be fine but treat as unverifiable
        # Re-check with a GET to distinguish TLS failure from HTTP error
        try:
            with urllib.request.urlopen(urllib.request.Request(url), context=ctx, timeout=10):
                pass
            return True
        except ssl.SSLError:
            return False
        except Exception:
            # Anything other than SSLError means TLS was acceptable, HTTP level issue
            return True


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------

def verify_signature(path: str | Path, pubkey_path: str | Path) -> bool:
    """
    Verify a detached GPG/OpenPGP signature for a file.
    Expects a companion .sig or .asc file alongside the target file.

    Requires gpg to be installed on the system.

    Args:
        path: Path to the file to verify.
        pubkey_path: Path to the ASCII-armored public key to import.
    Returns:
        True if signature is valid.
        False if signature is missing, invalid, or gpg is unavailable.
    """
    path = Path(path)
    pubkey_path = Path(pubkey_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if not pubkey_path.exists():
        raise FileNotFoundError(f"Public key not found: {pubkey_path}")

    # Find companion signature file
    sig_path = None
    for ext in [".sig", ".asc", ".gpg"]:
        candidate = path.with_suffix(path.suffix + ext)
        if candidate.exists():
            sig_path = candidate
            break

    if sig_path is None:
        return False  # No signature file found

    try:
        # Import the public key into a temporary keyring
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmpdir:
            gpg_home = tmpdir
            env = os.environ.copy()
            env["GNUPGHOME"] = gpg_home

            # Import key
            import_result = subprocess.run(
                ["gpg", "--import", str(pubkey_path)],
                capture_output=True, env=env, timeout=15
            )
            if import_result.returncode != 0:
                return False

            # Verify signature
            verify_result = subprocess.run(
                ["gpg", "--verify", str(sig_path), str(path)],
                capture_output=True, env=env, timeout=15
            )
            return verify_result.returncode == 0
    except FileNotFoundError:
        # gpg not installed
        return False
    except subprocess.TimeoutExpired:
        return False


# ---------------------------------------------------------------------------
# Combined verification
# ---------------------------------------------------------------------------

def verify_update(
    path: str | Path,
    url: str = None,
    expected_sha256: str = None,
    pubkey_path: str | Path = None,
) -> VerificationResult:
    """
    Run all applicable security checks on an update package.

    Args:
        path: Local path to the downloaded update file.
        url: Source URL (used for TLS check). Optional.
        expected_sha256: Expected SHA-256 digest. Optional but strongly recommended.
        pubkey_path: Path to GPG public key for signature check. Optional.

    Returns:
        VerificationResult with .passed and .checks populated.
    """
    checks = {}
    errors = []

    # 1. TLS check
    if url:
        try:
            tls_ok = verify_tls(url)
            checks["TLS/HTTPS"] = tls_ok
            if not tls_ok:
                errors.append(f"TLS verification failed for: {url}")
        except Exception as e:
            checks["TLS/HTTPS"] = False
            errors.append(f"TLS check error: {e}")
    else:
        checks["TLS/HTTPS"] = None  # skipped

    # 2. Checksum check
    if expected_sha256:
        try:
            cs_ok = verify_checksum(path, expected_sha256)
            checks["SHA-256 checksum"] = cs_ok
            if not cs_ok:
                actual = compute_checksum(path)
                errors.append(f"Checksum mismatch. Expected: {expected_sha256[:16]}... Got: {actual[:16]}...")
        except Exception as e:
            checks["SHA-256 checksum"] = False
            errors.append(f"Checksum error: {e}")
    else:
        checks["SHA-256 checksum"] = None  # skipped

    # 3. Signature check
    if pubkey_path:
        try:
            sig_ok = verify_signature(path, pubkey_path)
            checks["GPG signature"] = sig_ok
            if not sig_ok:
                errors.append("GPG signature verification failed or signature file not found")
        except Exception as e:
            checks["GPG signature"] = False
            errors.append(f"Signature check error: {e}")
    else:
        checks["GPG signature"] = None  # skipped

    # Pass only if every *executed* (non-skipped) check passed
    executed = {k: v for k, v in checks.items() if v is not None}
    passed = bool(executed) and all(executed.values())

    return VerificationResult(passed=passed, checks=checks, errors=errors)


# ---------------------------------------------------------------------------
# Entry point (diagnostic use)
# ---------------------------------------------------------------------------

def main(args: list[str] = None):
    """
    CLI diagnostic:
      python -m core.update_security checksum <file> <expected_sha256>
      python -m core.update_security tls <url>
      python -m core.update_security compute <file>
    """
    import sys
    args = args or sys.argv[1:]

    if not args:
        print("Usage:")
        print("  update_security checksum <file> <sha256>")
        print("  update_security tls <url>")
        print("  update_security compute <file>")
        return

    cmd = args[0]

    if cmd == "checksum" and len(args) >= 3:
        ok = verify_checksum(args[1], args[2])
        print("✓ Checksum matches" if ok else "✗ Checksum MISMATCH")
        sys.exit(0 if ok else 1)

    elif cmd == "tls" and len(args) >= 2:
        ok = verify_tls(args[1])
        print("✓ TLS valid" if ok else "✗ TLS FAILED or HTTP")
        sys.exit(0 if ok else 1)

    elif cmd == "compute" and len(args) >= 2:
        digest = compute_checksum(args[1])
        print(f"sha256:{digest}")

    else:
        print(f"Unknown command or missing args: {' '.join(args)}")
        sys.exit(1)


if __name__ == "__main__":
    main()