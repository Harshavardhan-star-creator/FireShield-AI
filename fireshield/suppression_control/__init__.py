"""Virtual-only suppression state management."""

from fireshield.suppression_control.engine import (
    ACTIVATED,
    ARMED,
    STANDBY,
    VirtualSuppressionController,
)

__all__ = ["ACTIVATED", "ARMED", "STANDBY", "VirtualSuppressionController"]
