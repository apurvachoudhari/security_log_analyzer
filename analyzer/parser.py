"""
LogParser — ingests a log file and normalizes lines into LogEvent objects.

Supports two common formats out of the box:
  1. syslog / auth.log  (Linux SSH, sudo, PAM)
  2. Apache/Nginx combined access log

Adding a new format: subclass BaseLogParser and register it in LogParser._detect_format().
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Iterator

from .models import LogEvent


# ─── Format-specific regexes ──────────────────────────────────────────────────

# syslog: "May 10 03:21:44 hostname sshd[1234]: Failed password for root from 1.2.3.4 port 22 ssh2"
_SYSLOG_RE = re.compile(
    r"(?P<month>\w+)\s+(?P<day>\d+)\s+(?P<time>\d{2}:\d{2}:\d{2})\s+"
    r"(?P<host>\S+)\s+(?P<process>\S+):\s+(?P<message>.+)"
)

# Apache/Nginx: '1.2.3.4 - frank [10/May/2025:03:21:44 +0000] "GET /admin HTTP/1.1" 401 512'
_ACCESS_LOG_RE = re.compile(
    r'(?P<ip>\S+)\s+\S+\s+(?P<user>\S+)\s+\[(?P<time>[^\]]+)\]\s+'
    r'"(?P<method>\S+)\s+(?P<path>\S+)[^"]*"\s+(?P<status>\d{3})\s+(?P<size>\d+|-)'
)

# Generic fallback: ISO timestamp + IP somewhere in line
_GENERIC_RE = re.compile(
    r"(?P<ts>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}).*?"
    r"(?P<ip>\b(?:\d{1,3}\.){3}\d{1,3}\b)"
)

# Patterns that indicate event types within a syslog message
_EVENT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"Failed password|authentication failure|Invalid user", re.I), "LOGIN_FAILED"),
    (re.compile(r"Accepted password|Accepted publickey|session opened for user", re.I), "LOGIN_SUCCESS"),
    (re.compile(r"\bsudo\b", re.I), "SUDO_COMMAND"),
    (re.compile(r"connection closed|disconnected|timeout", re.I), "CONNECTION_CLOSED"),
    (re.compile(r"scan|nmap|masscan", re.I), "PORT_SCAN"),
    (re.compile(r"new user|useradd|groupadd", re.I), "USER_CREATED"),
    (re.compile(r"passwd|chpasswd|password changed", re.I), "PASSWORD_CHANGE"),
    (re.compile(r"error|ERROR|WARN|warning", re.I), "ERROR"),
]

_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_USER_RE = re.compile(r"(?:for|user)\s+(\S+)", re.I)


class LogParser:
    """
    Reads a log file line by line and yields normalised LogEvent objects.
    Automatically detects the format from the first non-empty line.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._format: str | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    def parse(self) -> list[LogEvent]:
        return list(self._iter_events())

    # ── Private helpers ───────────────────────────────────────────────────────

    def _iter_events(self) -> Iterator[LogEvent]:
        with self.path.open("r", encoding="utf-8", errors="replace") as fh:
            for lineno, raw in enumerate(fh, start=1):
                raw = raw.rstrip()
                if not raw:
                    continue

                if self._format is None:
                    self._format = self._detect_format(raw)

                event = self._parse_line(raw, lineno)
                if event:
                    yield event

    def _detect_format(self, first_line: str) -> str:
        if _SYSLOG_RE.match(first_line):
            return "syslog"
        if _ACCESS_LOG_RE.match(first_line):
            return "access"
        return "generic"

    def _parse_line(self, raw: str, lineno: int) -> LogEvent | None:
        if self._format == "syslog":
            return self._parse_syslog(raw)
        if self._format == "access":
            return self._parse_access(raw)
        return self._parse_generic(raw)

    def _parse_syslog(self, raw: str) -> LogEvent | None:
        m = _SYSLOG_RE.match(raw)
        if not m:
            return None

        # Build timestamp (assume current year — syslog omits it)
        current_year = datetime.now().year
        try:
            ts = datetime.strptime(
                f"{current_year} {m['month']} {m['day']} {m['time']}",
                "%Y %b %d %H:%M:%S",
            )
        except ValueError:
            return None

        message = m["message"]
        process = m["process"]
        event_type = self._classify_message(f"{process} {message}")
        source_ip = self._extract_ip(message)
        username = self._extract_user(message)

        return LogEvent(
            timestamp=ts,
            source_ip=source_ip or "unknown",
            event_type=event_type,
            username=username,
            raw=raw,
        )

    def _parse_access(self, raw: str) -> LogEvent | None:
        m = _ACCESS_LOG_RE.match(raw)
        if not m:
            return None

        try:
            ts = datetime.strptime(m["time"], "%d/%b/%Y:%H:%M:%S %z").replace(tzinfo=None)
        except ValueError:
            return None

        status = int(m["status"])
        path = m["path"]

        if status == 401 or status == 403:
            event_type = "LOGIN_FAILED"
        elif status < 400:
            event_type = "HTTP_SUCCESS"
        elif status >= 500:
            event_type = "SERVER_ERROR"
        else:
            event_type = "HTTP_ERROR"

        # Flag suspicious paths
        if any(p in path.lower() for p in ["/admin", "/wp-login", "/.env", "/phpmyadmin", "/etc/passwd"]):
            event_type = "SUSPICIOUS_REQUEST"

        user = m["user"] if m["user"] != "-" else None

        return LogEvent(
            timestamp=ts,
            source_ip=m["ip"],
            event_type=event_type,
            username=user,
            raw=raw,
        )

    def _parse_generic(self, raw: str) -> LogEvent | None:
        m = _GENERIC_RE.search(raw)
        if not m:
            return None
        try:
            ts_str = m["ts"].replace("T", " ")
            ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None

        return LogEvent(
            timestamp=ts,
            source_ip=m["ip"],
            event_type=self._classify_message(raw),
            username=self._extract_user(raw),
            raw=raw,
        )

    @staticmethod
    def _classify_message(message: str) -> str:
        for pattern, event_type in _EVENT_PATTERNS:
            if pattern.search(message):
                return event_type
        return "INFO"

    @staticmethod
    def _extract_ip(text: str) -> str | None:
        m = _IP_RE.search(text)
        return m.group(0) if m else None

    @staticmethod
    def _extract_user(text: str) -> str | None:
        m = _USER_RE.search(text)
        if m:
            user = m.group(1).strip(".,;:")
            # Filter out noise
            if user.lower() not in {"from", "to", "the", "a", "an"}:
                return user
        return None
