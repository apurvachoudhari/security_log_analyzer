# 🛡️ Security Log Analyzer

A modular Python tool that ingests server logs, detects anomalies and threat patterns, and produces structured reports in text, JSON, or HTML format.

Built to demonstrate **security-first data engineering** practices: clean separation of concerns, testable modules, CI/CD-compatible exit codes, and zero external runtime dependencies.

---

## Features

| Detection Rule | Severity |
|---|---|
| Brute force SSH (rolling window) | CRITICAL / HIGH |
| Credential stuffing (multi-user from one IP) | HIGH |
| Successful login after repeated failures | HIGH |
| Port scan activity | HIGH |
| Off-hours logins (midnight–5 AM) | MEDIUM |
| Suspicious HTTP requests (admin paths, `.env`, etc.) | MEDIUM |
| New user / group creation | MEDIUM |
| Password changes | LOW |

**Report formats:** Plain text · JSON · HTML dashboard

**Log formats supported:** syslog / auth.log · Apache/Nginx access log · Generic ISO-timestamp logs

---

## Project Structure

```
security_log_analyzer/
├── main.py                  # CLI entry point
├── requirements.txt
├── sample_logs/
│   └── sample.log           # Realistic demo log
├── reports/                 # Generated reports land here
├── analyzer/
│   ├── models.py            # Shared dataclasses (LogEvent, Finding)
│   ├── parser.py            # Log ingestion + normalization
│   ├── detector.py          # Anomaly detection rules
│   └── reporter.py          # Report rendering (text/JSON/HTML)
└── tests/
    └── test_analyzer.py     # Unit tests (pytest)
```

---

## Quick Start

```bash
# Clone and enter the project
git clone https://github.com/apurvachoudhari/security-log-analyzer.git
cd security_log_analyzer

# Install dev dependencies
pip install -r requirements.txt

# Run on the sample log (text output)
python main.py --log sample_logs/sample.log

# HTML report (opens nicely in a browser)
python main.py --log sample_logs/sample.log --format html --out reports/

# JSON output (pipeline-friendly)
python main.py --log sample_logs/sample.log --format json

# Adjust brute-force threshold
python main.py --log sample_logs/sample.log --threshold 10
```

---

## Running Tests

```bash
# All tests
pytest tests/ -v

# With coverage report
pytest tests/ --cov=analyzer --cov-report=term-missing
```

---

## CI/CD Integration

`main.py` returns exit code `2` when **CRITICAL** findings are detected, making it drop-in compatible as a pipeline gate:

```yaml
# GitHub Actions example
- name: Analyze security logs
  run: python main.py --log /var/log/auth.log --format json
  # Step fails (blocks deploy) if critical findings found
```

---

## Extending

**Add a new detection rule** — add a method to `AnomalyDetector` in `detector.py`:

```python
def _detect_my_rule(self, events: list[LogEvent]) -> list[Finding]:
    ...
    return [Finding(...)]
```

Then register it in `self._detectors` in `__init__`.

**Add a new log format** — add a regex + parse method to `parser.py` and register it in `_detect_format()`.

---

## Design Decisions

- **Zero external runtime dependencies** — standard library only (`re`, `datetime`, `collections`, `json`, `pathlib`). Easy to deploy in restricted environments.
- **Sliding window detection** — brute force uses a true rolling window (not just total count) to reduce false positives.
- **Separation of concerns** — parser, detector, and reporter are fully independent; each can be unit tested in isolation.
- **CI/CD exit codes** — critical findings return exit code 2 for automated pipeline gating.
- **Extensible by design** — new rules and formats follow a documented pattern.

---

*Built by [Apurva Choudhari](https://apurvachoudhari.com) · [LinkedIn](https://linkedin.com/in/apurva-choudhari)*
