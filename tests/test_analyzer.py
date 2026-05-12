"""
Tests for parser, detector, and reporter.
Run with: pytest tests/ -v
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from analyzer.detector import AnomalyDetector, _count_in_window
from analyzer.models import Finding, LogEvent
from analyzer.parser import LogParser
from analyzer.reporter import ReportGenerator


# ── Fixtures ───────────────────────────────────────────────────────────────────

def make_event(
    event_type: str,
    source_ip: str = "1.2.3.4",
    username: str | None = "root",
    hour: int = 12,
    minute: int = 0,
    second: int = 0,
) -> LogEvent:
    return LogEvent(
        timestamp=datetime(2025, 5, 10, hour, minute, second),
        source_ip=source_ip,
        event_type=event_type,
        username=username,
        raw=f"fake log line {event_type} from {source_ip}",
    )


# ── Parser tests ───────────────────────────────────────────────────────────────

class TestLogParser:
    def test_parses_syslog_failed_password(self, tmp_path: Path):
        log = tmp_path / "auth.log"
        log.write_text(
            "May 10 02:14:01 webserver sshd[1201]: Failed password for root from 1.2.3.4 port 22 ssh2\n"
        )
        events = LogParser(log).parse()
        assert len(events) == 1
        assert events[0].event_type == "LOGIN_FAILED"
        assert events[0].source_ip == "1.2.3.4"
        assert events[0].username == "root"

    def test_parses_syslog_successful_login(self, tmp_path: Path):
        log = tmp_path / "auth.log"
        log.write_text(
            "May 10 09:00:00 webserver sshd[999]: Accepted password for alice from 10.0.0.1 port 22 ssh2\n"
        )
        events = LogParser(log).parse()
        assert events[0].event_type == "LOGIN_SUCCESS"

    def test_skips_empty_lines(self, tmp_path: Path):
        log = tmp_path / "auth.log"
        log.write_text(
            "May 10 09:00:00 webserver sshd[1]: Failed password for bob from 1.1.1.1 port 22 ssh2\n"
            "\n"
            "\n"
            "May 10 09:00:01 webserver sshd[2]: Failed password for bob from 1.1.1.1 port 22 ssh2\n"
        )
        events = LogParser(log).parse()
        assert len(events) == 2

    def test_parses_sudo_command(self, tmp_path: Path):
        log = tmp_path / "auth.log"
        log.write_text(
            "May 10 10:00:00 server sudo[123]: alice : TTY=pts/0 ; USER=root ; COMMAND=/bin/bash\n"
        )
        events = LogParser(log).parse()
        assert events[0].event_type == "SUDO_COMMAND"

    def test_parses_access_log_suspicious_path(self, tmp_path: Path):
        log = tmp_path / "access.log"
        log.write_text(
            '1.2.3.4 - - [10/May/2025:12:00:00 +0000] "GET /admin HTTP/1.1" 401 512\n'
        )
        events = LogParser(log).parse()
        assert events[0].event_type == "SUSPICIOUS_REQUEST"
        assert events[0].source_ip == "1.2.3.4"

    def test_handles_unreadable_lines_gracefully(self, tmp_path: Path):
        log = tmp_path / "auth.log"
        log.write_text(
            "May 10 09:00:00 server sshd[1]: Failed password for x from 1.1.1.1 port 22 ssh2\n"
            "this line is garbage and should be skipped\n"
            "May 10 09:00:01 server sshd[2]: Failed password for x from 1.1.1.1 port 22 ssh2\n"
        )
        # Should not raise; garbage line silently skipped
        events = LogParser(log).parse()
        assert len(events) == 2


# ── Detector tests ─────────────────────────────────────────────────────────────

class TestAnomalyDetector:
    def setup_method(self):
        self.detector = AnomalyDetector(brute_force_threshold=5)

    def test_detects_brute_force(self):
        events = [
            make_event("LOGIN_FAILED", source_ip="9.9.9.9", minute=i)
            for i in range(10)
        ]
        findings = self.detector.analyze(events)
        titles = [f.title for f in findings]
        assert any("Brute Force" in t for t in titles)

    def test_no_brute_force_below_threshold(self):
        events = [
            make_event("LOGIN_FAILED", source_ip="9.9.9.9", minute=i)
            for i in range(3)
        ]
        findings = self.detector.analyze(events)
        assert not any("Brute Force" in f.title for f in findings)

    def test_detects_credential_stuffing(self):
        users = ["alice", "bob", "charlie", "dave"]
        events = [
            make_event("LOGIN_FAILED", source_ip="5.5.5.5", username=u)
            for u in users
        ]
        findings = self.detector.analyze(events)
        assert any("Credential Stuffing" in f.title for f in findings)

    def test_detects_success_after_failures(self):
        events = [
            make_event("LOGIN_FAILED", source_ip="7.7.7.7", minute=i)
            for i in range(5)
        ] + [make_event("LOGIN_SUCCESS", source_ip="7.7.7.7", minute=6)]
        findings = self.detector.analyze(events)
        assert any("Successful Login After" in f.title for f in findings)

    def test_detects_off_hours_login(self):
        events = [make_event("LOGIN_SUCCESS", source_ip="2.2.2.2", hour=2)]
        findings = self.detector.analyze(events)
        assert any("Off-Hours" in f.title for f in findings)

    def test_no_off_hours_during_business_hours(self):
        events = [make_event("LOGIN_SUCCESS", source_ip="2.2.2.2", hour=10)]
        findings = self.detector.analyze(events)
        assert not any("Off-Hours" in f.title for f in findings)

    def test_detects_new_user_creation(self):
        events = [make_event("USER_CREATED")]
        findings = self.detector.analyze(events)
        assert any("New User" in f.title for f in findings)

    def test_critical_severity_for_large_brute_force(self):
        events = [
            make_event("LOGIN_FAILED", source_ip="6.6.6.6", minute=0, second=i)
            for i in range(25)
        ]
        findings = self.detector.analyze(events)
        bf = [f for f in findings if "Brute Force" in f.title]
        assert bf and bf[0].severity == "CRITICAL"

    def test_findings_sorted_by_severity(self):
        events = (
            [make_event("LOGIN_FAILED", source_ip="8.8.8.8", minute=i) for i in range(10)]
            + [make_event("LOGIN_SUCCESS", source_ip="3.3.3.3", hour=3)]
        )
        findings = self.detector.analyze(events)
        severities = [f.severity for f in findings]
        rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
        assert all(rank[severities[i]] <= rank[severities[i + 1]] for i in range(len(severities) - 1))


# ── Reporter tests ─────────────────────────────────────────────────────────────

class TestReportGenerator:
    def _make_finding(self) -> Finding:
        ts = datetime(2025, 5, 10, 12, 0, 0)
        return Finding(
            title="Test Finding",
            severity="HIGH",
            description="Something suspicious happened.",
            source_ip="1.1.1.1",
            affected_user="root",
            event_count=5,
            first_seen=ts,
            last_seen=ts,
            evidence=["fake log line 1", "fake log line 2"],
        )

    def test_text_report_created(self, tmp_path: Path):
        events = [make_event("LOGIN_FAILED")]
        findings = [self._make_finding()]
        rg = ReportGenerator(events, findings, tmp_path)
        path = rg.generate(fmt="text")
        assert path.exists()
        content = path.read_text()
        assert "SECURITY LOG ANALYSIS REPORT" in content
        assert "Test Finding" in content

    def test_json_report_structure(self, tmp_path: Path):
        events = [make_event("LOGIN_FAILED")]
        findings = [self._make_finding()]
        rg = ReportGenerator(events, findings, tmp_path)
        path = rg.generate(fmt="json")
        data = json.loads(path.read_text())
        assert "summary" in data
        assert "findings" in data
        assert data["findings"][0]["title"] == "Test Finding"
        assert data["summary"]["total_events"] == 1

    def test_html_report_created(self, tmp_path: Path):
        events = [make_event("LOGIN_FAILED")]
        findings = [self._make_finding()]
        rg = ReportGenerator(events, findings, tmp_path)
        path = rg.generate(fmt="html")
        content = path.read_text()
        assert "<!DOCTYPE html>" in content
        assert "Test Finding" in content

    def test_empty_findings_does_not_crash(self, tmp_path: Path):
        events = [make_event("INFO")]
        rg = ReportGenerator(events, [], tmp_path)
        for fmt in ("text", "json", "html"):
            path = rg.generate(fmt=fmt)
            assert path.exists()


# ── Helper function tests ──────────────────────────────────────────────────────

class TestHelpers:
    def test_count_in_window_all_within(self):
        events = [make_event("LOGIN_FAILED", minute=i) for i in range(5)]
        assert _count_in_window(events, minutes=10) == 5

    def test_count_in_window_spread_out(self):
        # Events 1 hour apart; window is 10 min → max 1 per window
        events = [make_event("LOGIN_FAILED", hour=i) for i in range(5)]
        assert _count_in_window(events, minutes=10) == 1

    def test_count_in_window_empty(self):
        assert _count_in_window([], minutes=10) == 0
