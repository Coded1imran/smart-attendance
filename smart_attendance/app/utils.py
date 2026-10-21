import math
import time
import hmac
import hashlib
import base64
import io

def calculate_haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculates the great-circle distance between two GPS coordinates in meters.
    Formula: Haversine
    """
    R = 6371000.0  # Earth's mean radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2))
    
    # Clamp to avoid numerical floating-point inaccuracies
    a = min(1.0, max(0.0, a))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    return round(R * c, 2)


def get_rotating_code_data(secret_seed: str, interval: int = 30) -> tuple[str, int]:
    """
    Generates a deterministic 6-digit TOTP-style rotating code based on
    the session's secret seed and unix epoch timestamp.
    
    Returns:
        (6_digit_code_str, seconds_remaining_in_current_window)
    """
    now = int(time.time())
    time_step = now // interval
    seconds_remaining = interval - (now % interval)

    # Standard RFC 6238 truncated HMAC-SHA256
    msg = time_step.to_bytes(8, byteorder="big")
    digest = hmac.new(secret_seed.encode("utf-8"), msg, hashlib.sha256).digest()
    
    offset = digest[-1] & 0x0F
    binary = (
        ((digest[offset] & 0x7F) << 24)
        | ((digest[offset + 1] & 0xFF) << 16)
        | ((digest[offset + 2] & 0xFF) << 8)
        | (digest[offset + 3] & 0xFF)
    )
    code = str(binary % 1_000_000).zfill(6)
    return code, seconds_remaining


def verify_rotating_code(entered_code: str, secret_seed: str, interval: int = 30, tolerance_steps: int = 1) -> bool:
    """
    Verifies the user-entered 6-digit code against the current timestamp window.
    Supports a tolerance of +/- 1 window (30s) to accommodate latency right as the code rotates.
    """
    if not entered_code or len(entered_code.strip()) != 6:
        return False

    now = int(time.time())
    current_step = now // interval

    # Check current window, previous window (-1), and next window (+1)
    for delta in range(-tolerance_steps, tolerance_steps + 1):
        step = current_step + delta
        msg = step.to_bytes(8, byteorder="big")
        digest = hmac.new(secret_seed.encode("utf-8"), msg, hashlib.sha256).digest()
        offset = digest[-1] & 0x0F
        binary = (
            ((digest[offset] & 0x7F) << 24)
            | ((digest[offset + 1] & 0xFF) << 16)
            | ((digest[offset + 2] & 0xFF) << 8)
            | (digest[offset + 3] & 0xFF)
        )
        valid_code = str(binary % 1_000_000).zfill(6)
        if entered_code.strip() == valid_code:
            return True

    return False


def clean_base64_image(base64_str: str) -> bytes:
    """Strips data URI scheme prefix (e.g. data:image/jpeg;base64,) and decodes raw bytes."""
    if "," in base64_str:
        base64_str = base64_str.split(",", 1)[1]
    return base64.b64decode(base64_str)
