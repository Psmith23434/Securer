# COMPILE_TO_PYD
"""
Hardware fingerprinting for license binding.
Produces a stable machine ID from MAC address + platform info.
Compile this module to .pyd before distribution.
"""
import uuid
import hashlib
import platform


def get_machine_id() -> str:
    """
    Returns a stable, anonymized hardware fingerprint.
    Uses MAC address + platform node as entropy sources.
    The result is a 16-char hex string — stable across reboots.
    """
    raw = f"{uuid.getnode()}:{platform.node()}:{platform.machine()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


if __name__ == "__main__":
    print("Machine ID:", get_machine_id())
