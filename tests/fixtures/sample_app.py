"""
Sample application fixture used by tests.
This file intentionally contains diverse string patterns
to exercise the full range of the string encryptor.
"""
import os

# Module-level constants
APP_NAME = "Snippet Tool"
VERSION = "1.0.0"
BASE_URL = "https://api.example.com/validate"
SECRET_KEY = "do-not-ship-this-in-plaintext"


class LicenseChecker:
    """Validates license keys."""

    ERROR_INVALID = "Invalid license key format"
    ERROR_EXPIRED = "License has expired"
    SUCCESS = "License valid"

    def check(self, key: str) -> str:
        if not key.startswith("SEC-"):
            return self.ERROR_INVALID
        if key == "SEC-EXPIRED-0000":
            return self.ERROR_EXPIRED
        return self.SUCCESS


def get_update_url(channel: str = "stable") -> str:
    """Return the update manifest URL for the given channel."""
    channels = {
        "stable": "https://releases.example.com/stable/manifest.json",
        "beta": "https://releases.example.com/beta/manifest.json",
    }
    return channels.get(channel, "https://releases.example.com/stable/manifest.json")
