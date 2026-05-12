"""
Shared data models used across parser, detector, and reporter.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class LogEvent:
    """A single parsed log line."""

    timestamp: datetime
    source_ip: str
    event_type: str          # e.g. LOGIN_FAILED, LOGIN_SUCCESS, PORT_SCAN, etc.
    username: Optional[str]
    raw: str                 # original log line


@dataclass
class Finding:
    """A detected anomaly or threat signal."""

    title: str
    severity: str            # CRITICAL | HIGH | MEDIUM | LOW | INFO
    description: str
    source_ip: Optional[str]
    affected_user: Optional[str]
    event_count: int
    first_seen: datetime
    last_seen: datetime
    evidence: list[str] = field(default_factory=list)   # sample raw log lines

    @property
    def duration_seconds(self) -> float:
        return (self.last_seen - self.first_seen).total_seconds()
