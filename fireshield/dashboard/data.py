"""Deterministic, illustrative facility readings for the dashboard."""

from datetime import datetime, timedelta

import pandas as pd


ZONES = [
    {"zone": "Production Unit", "temperature": 31.8, "smoke": 8, "gas": 14, "humidity": 46, "risk": 22},
    {"zone": "Chemical Storage", "temperature": 38.4, "smoke": 21, "gas": 68, "humidity": 39, "risk": 58},
    {"zone": "Electrical Room", "temperature": 45.7, "smoke": 46, "gas": 32, "humidity": 34, "risk": 82},
    {"zone": "Packaging Unit", "temperature": 29.6, "smoke": 12, "gas": 18, "humidity": 51, "risk": 34},
]


def get_zone_data() -> pd.DataFrame:
    """Return fixed simulated readings; risk is illustrative, not an AI output."""
    return pd.DataFrame(ZONES)


def get_alert_history() -> pd.DataFrame:
    """Create a small recent-alert sample with relative timestamps."""
    now = datetime.now().astimezone()
    records = [
        (now - timedelta(minutes=4), "Electrical Room", "ACT", "Critical temperature trend"),
        (now - timedelta(minutes=18), "Chemical Storage", "ALERT", "Elevated gas reading"),
        (now - timedelta(hours=1, minutes=12), "Packaging Unit", "WATCH", "Smoke level returned to baseline"),
        (now - timedelta(hours=2, minutes=5), "Production Unit", "WATCH", "Routine zone status recorded"),
    ]
    return pd.DataFrame(records, columns=["Timestamp", "Zone", "Severity", "Event"])
