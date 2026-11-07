"""Make the server use Pakistan time. Cloud servers run on UTC, which would show yesterday's date between midnight and 5 am in Pakistan."""
import os
import time


def apply_timezone():
    """Set the process time zone (Linux and macOS servers). Windows already uses the computer's own time. Returns the zone used, or None."""
    zone = os.environ.get("PLANTPULSE_TZ") or "Asia/Karachi"
    if not hasattr(time, "tzset"):
        return None
    os.environ["TZ"] = zone
    time.tzset()
    return zone
