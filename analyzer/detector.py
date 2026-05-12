"""
AnomalyDetector — runs a suite of detection rules over parsed LogEvents
and returns a list of Findings.

Each detector method follows the same contract:
    def _detect_<name>(self, events: list[LogEvent]) -> list[Finding]

Adding a new rule: write the method and add it to _DETECTORS.
"""

from collections import defaultdict
from datetime import timedelta
from typing import Callable

from .models import Finding, LogEvent

# Max evidence lines stored per finding (keeps memory bounded)
_MAX_EVIDENCE = 5


class AnomalyDetector:
    def __init__(self, brute_force_threshold: int = 5) -> None:
        self.brute_force_threshold = brute_force_threshold

        # Registry of detection rules — order determines report order
        self._detectors: list[Callable] = [
            self._detect_brute_force,
            self._detect_credential_stuffing,
            self._detect_successful_login_after_failures,
            self._detect_off_hours_logins,
            self._detect_new_user_creation,
            self._detect_suspicious_http_requests,
            self._detect_password_changes,
            self._detect_port_scan_activity,
        ]

    # ── Public API ─────────────────────────────────────────────────────────────

    def analyze(self, events: list[LogEvent]) -> list[Finding]:
        findings: list[Finding] = []
        for detector in self._detectors:
            findings.extend(detector(events))
        return sorted(findings, key=lambda f: _severity_rank(f.severity))

    # ── Detection Rules ────────────────────────────────────────────────────────

    def _detect_brute_force(self, events: list[LogEvent]) -> list[Finding]:
        """Multiple failed logins from the same IP within a short window."""
        failures: dict[str, list[LogEvent]] = defaultdict(list)
        for e in events:
            if e.event_type == "LOGIN_FAILED":
                failures[e.source_ip].append(e)

        findings = []
        for ip, evts in failures.items():
            if len(evts) >= self.brute_force_threshold:
                # Check if attempts are within a 10-minute window
                evts_sorted = sorted(evts, key=lambda x: x.timestamp)
                window_hits = _count_in_window(evts_sorted, minutes=10)
                if window_hits >= self.brute_force_threshold:
                    severity = "CRITICAL" if window_hits >= 20 else "HIGH"
                    findings.append(
                        Finding(
                            title=f"Brute Force Attack from {ip}",
                            severity=severity,
                            description=(
                                f"{window_hits} failed login attempts from {ip} "
                                f"within a 10-minute window."
                            ),
                            source_ip=ip,
                            affected_user=_most_common_user(evts),
                            event_count=window_hits,
                            first_seen=evts_sorted[0].timestamp,
                            last_seen=evts_sorted[-1].timestamp,
                            evidence=[e.raw for e in evts_sorted[:_MAX_EVIDENCE]],
                        )
                    )
        return findings

    def _detect_credential_stuffing(self, events: list[LogEvent]) -> list[Finding]:
        """One IP trying many different usernames — credential stuffing pattern."""
        ip_users: dict[str, set[str]] = defaultdict(set)
        ip_events: dict[str, list[LogEvent]] = defaultdict(list)

        for e in events:
            if e.event_type == "LOGIN_FAILED" and e.username:
                ip_users[e.source_ip].add(e.username)
                ip_events[e.source_ip].append(e)

        findings = []
        for ip, users in ip_users.items():
            if len(users) >= 3:
                evts = sorted(ip_events[ip], key=lambda x: x.timestamp)
                findings.append(
                    Finding(
                        title=f"Credential Stuffing from {ip}",
                        severity="HIGH",
                        description=(
                            f"{ip} attempted logins against {len(users)} different "
                            f"usernames: {', '.join(sorted(users)[:5])}{'...' if len(users) > 5 else ''}"
                        ),
                        source_ip=ip,
                        affected_user=None,
                        event_count=len(evts),
                        first_seen=evts[0].timestamp,
                        last_seen=evts[-1].timestamp,
                        evidence=[e.raw for e in evts[:_MAX_EVIDENCE]],
                    )
                )
        return findings

    def _detect_successful_login_after_failures(self, events: list[LogEvent]) -> list[Finding]:
        """Successful login from an IP that previously had failures — possible compromise."""
        failures_by_ip: dict[str, list[LogEvent]] = defaultdict(list)
        successes_by_ip: dict[str, list[LogEvent]] = defaultdict(list)

        for e in events:
            if e.event_type == "LOGIN_FAILED":
                failures_by_ip[e.source_ip].append(e)
            elif e.event_type == "LOGIN_SUCCESS":
                successes_by_ip[e.source_ip].append(e)

        findings = []
        for ip in set(failures_by_ip) & set(successes_by_ip):
            fail_count = len(failures_by_ip[ip])
            if fail_count >= 3:
                all_evts = sorted(
                    failures_by_ip[ip] + successes_by_ip[ip],
                    key=lambda x: x.timestamp,
                )
                findings.append(
                    Finding(
                        title=f"Successful Login After {fail_count} Failures from {ip}",
                        severity="HIGH",
                        description=(
                            f"{ip} failed {fail_count} times before achieving a "
                            f"successful login — possible brute force success."
                        ),
                        source_ip=ip,
                        affected_user=_most_common_user(successes_by_ip[ip]),
                        event_count=fail_count + len(successes_by_ip[ip]),
                        first_seen=all_evts[0].timestamp,
                        last_seen=all_evts[-1].timestamp,
                        evidence=[e.raw for e in all_evts[:_MAX_EVIDENCE]],
                    )
                )
        return findings

    def _detect_off_hours_logins(self, events: list[LogEvent]) -> list[Finding]:
        """Successful logins between 00:00–05:00 — unusual for most orgs."""
        off_hours = [
            e for e in events
            if e.event_type == "LOGIN_SUCCESS" and e.timestamp.hour < 5
        ]
        if not off_hours:
            return []

        by_user: dict[str, list[LogEvent]] = defaultdict(list)
        for e in off_hours:
            key = e.username or e.source_ip
            by_user[key].append(e)

        findings = []
        for user, evts in by_user.items():
            evts_sorted = sorted(evts, key=lambda x: x.timestamp)
            findings.append(
                Finding(
                    title=f"Off-Hours Login — {user}",
                    severity="MEDIUM",
                    description=(
                        f"{len(evts)} successful login(s) detected between midnight "
                        f"and 5 AM for '{user}'."
                    ),
                    source_ip=evts[0].source_ip,
                    affected_user=evts[0].username,
                    event_count=len(evts),
                    first_seen=evts_sorted[0].timestamp,
                    last_seen=evts_sorted[-1].timestamp,
                    evidence=[e.raw for e in evts_sorted[:_MAX_EVIDENCE]],
                )
            )
        return findings

    def _detect_new_user_creation(self, events: list[LogEvent]) -> list[Finding]:
        """New user or group creation events — potential privilege escalation."""
        user_events = [e for e in events if e.event_type == "USER_CREATED"]
        if not user_events:
            return []

        evts_sorted = sorted(user_events, key=lambda x: x.timestamp)
        return [
            Finding(
                title="New User/Group Created",
                severity="MEDIUM",
                description=f"{len(user_events)} user or group creation event(s) detected.",
                source_ip=user_events[0].source_ip,
                affected_user=user_events[0].username,
                event_count=len(user_events),
                first_seen=evts_sorted[0].timestamp,
                last_seen=evts_sorted[-1].timestamp,
                evidence=[e.raw for e in evts_sorted[:_MAX_EVIDENCE]],
            )
        ]

    def _detect_suspicious_http_requests(self, events: list[LogEvent]) -> list[Finding]:
        """Requests to sensitive paths — admin panels, env files, etc."""
        suspicious = [e for e in events if e.event_type == "SUSPICIOUS_REQUEST"]
        if not suspicious:
            return []

        by_ip: dict[str, list[LogEvent]] = defaultdict(list)
        for e in suspicious:
            by_ip[e.source_ip].append(e)

        findings = []
        for ip, evts in by_ip.items():
            evts_sorted = sorted(evts, key=lambda x: x.timestamp)
            findings.append(
                Finding(
                    title=f"Suspicious HTTP Requests from {ip}",
                    severity="MEDIUM",
                    description=(
                        f"{len(evts)} request(s) to sensitive paths "
                        f"(admin panels, config files, etc.) from {ip}."
                    ),
                    source_ip=ip,
                    affected_user=None,
                    event_count=len(evts),
                    first_seen=evts_sorted[0].timestamp,
                    last_seen=evts_sorted[-1].timestamp,
                    evidence=[e.raw for e in evts_sorted[:_MAX_EVIDENCE]],
                )
            )
        return findings

    def _detect_password_changes(self, events: list[LogEvent]) -> list[Finding]:
        """Unexpected password change events."""
        pw_events = [e for e in events if e.event_type == "PASSWORD_CHANGE"]
        if not pw_events:
            return []

        evts_sorted = sorted(pw_events, key=lambda x: x.timestamp)
        return [
            Finding(
                title="Password Change Detected",
                severity="LOW",
                description=f"{len(pw_events)} password change event(s) logged.",
                source_ip=pw_events[0].source_ip,
                affected_user=pw_events[0].username,
                event_count=len(pw_events),
                first_seen=evts_sorted[0].timestamp,
                last_seen=evts_sorted[-1].timestamp,
                evidence=[e.raw for e in evts_sorted[:_MAX_EVIDENCE]],
            )
        ]

    def _detect_port_scan_activity(self, events: list[LogEvent]) -> list[Finding]:
        """Port scan signatures detected in logs."""
        scan_events = [e for e in events if e.event_type == "PORT_SCAN"]
        if not scan_events:
            return []

        evts_sorted = sorted(scan_events, key=lambda x: x.timestamp)
        return [
            Finding(
                title="Port Scan Activity Detected",
                severity="HIGH",
                description=(
                    f"{len(scan_events)} port scan signature(s) detected — "
                    f"possible reconnaissance activity."
                ),
                source_ip=scan_events[0].source_ip,
                affected_user=None,
                event_count=len(scan_events),
                first_seen=evts_sorted[0].timestamp,
                last_seen=evts_sorted[-1].timestamp,
                evidence=[e.raw for e in evts_sorted[:_MAX_EVIDENCE]],
            )
        ]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _severity_rank(severity: str) -> int:
    return {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}.get(severity, 5)


def _most_common_user(events: list[LogEvent]) -> str | None:
    users = [e.username for e in events if e.username]
    if not users:
        return None
    return max(set(users), key=users.count)


def _count_in_window(sorted_events: list[LogEvent], minutes: int) -> int:
    """Return the largest count of events within any rolling `minutes` window."""
    if not sorted_events:
        return 0
    window = timedelta(minutes=minutes)
    max_count = 0
    left = 0
    for right in range(len(sorted_events)):
        while (
            sorted_events[right].timestamp - sorted_events[left].timestamp > window
        ):
            left += 1
        max_count = max(max_count, right - left + 1)
    return max_count
