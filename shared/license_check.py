# COMPILE_TO_PYD
"""
HMAC-based license key validation.
Compile this module to .pyd before distribution — never ship as plain .py.

Key format: XXXX-XXXX-XXXX-XXXX (base32-encoded HMAC fragment)
Generation: tools/keygen.py (keep offline, never distribute)
"""
import hmac
import hashlib
import base64
from shared.machine_id import get_machine_id

# IMPORTANT: Replace with a real secret before production.
# Store this ONLY in this file — never in config, never in env vars in the exe.
_SECRET = b"REPLACE_WITH_YOUR_32_BYTE_SECRET_KEY_HERE"
_PRODUCT_ID = "snippet_tool_v1"


def _compute_expected_key(machine_id: str) -> str:
    payload = f"{_PRODUCT_ID}:{machine_id}".encode()
    digest = hmac.new(_SECRET, payload, hashlib.sha256).digest()
    b32 = base64.b32encode(digest[:10]).decode()
    # Format as XXXX-XXXX-XXXX-XXXX
    return "-".join(b32[i:i+4] for i in range(0, 16, 4))


def validate_license(key: str) -> bool:
    """
    Returns True if the given key is valid for this machine.
    In trial mode, always returns False (use is_trial_valid instead).
    """
    if not key or len(key) < 10:
        return False
    machine_id = get_machine_id()
    expected = _compute_expected_key(machine_id)
    # Constant-time comparison to prevent timing attacks
    return hmac.compare_digest(
        key.strip().upper().replace(" ", "-"),
        expected
    )


def get_activation_info(key: str) -> dict:
    """Returns a dict with activation status and machine ID for display."""
    machine_id = get_machine_id()
    return {
        "valid": validate_license(key),
        "machine_id": machine_id,
        "key_provided": bool(key),
    }


if __name__ == "__main__":
    mid = get_machine_id()
    key = _compute_expected_key(mid)
    print(f"Machine ID : {mid}")
    print(f"Valid key  : {key}")
    print(f"Self-check : {validate_license(key)}")
