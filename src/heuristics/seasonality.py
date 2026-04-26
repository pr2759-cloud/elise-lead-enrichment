"""Leasing seasonality: peak Apr-Aug, shoulder Mar/Sep/Oct, off-season Nov-Feb."""
from __future__ import annotations
from datetime import datetime
from typing import Optional


def seasonality_score(when: Optional[datetime] = None) -> float:
    """Timing sub-signal: 0-10 based on where we are in the leasing calendar."""
    when = when or datetime.utcnow()
    month = when.month
    if month in (4, 5, 6, 7, 8):
        return 10.0
    if month in (3, 9, 10):
        return 7.0
    return 4.0


def seasonality_label(when: Optional[datetime] = None) -> str:
    s = seasonality_score(when)
    return {10.0: "Peak leasing season", 7.0: "Shoulder season", 4.0: "Off-season"}[s]
