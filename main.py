"""
Security Log Analyzer — main entry point.
Usage:
    python main.py --log sample_logs/sample.log
    python main.py --log sample_logs/sample.log --format json
    python main.py --log sample_logs/sample.log --format html --out reports/
"""

import argparse
import sys
from pathlib import Path

from analyzer.parser import LogParser
from analyzer.detector import AnomalyDetector
from analyzer.reporter import ReportGenerator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Security Log Analyzer — detect anomalies and generate threat reports."
    )
    parser.add_argument("--log", required=True, help="Path to the log file to analyze")
    parser.add_argument(
        "--format",
        choices=["text", "json", "html"],
        default="text",
        help="Output report format (default: text)",
    )
    parser.add_argument(
        "--out",
        default="reports/",
        help="Directory to write the report (default: reports/)",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=5,
        help="Failed login attempts before flagging brute force (default: 5)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    log_path = Path(args.log)
    if not log_path.exists():
        print(f"[ERROR] Log file not found: {log_path}", file=sys.stderr)
        return 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[*] Parsing log file: {log_path}")
    parser = LogParser(log_path)
    events = parser.parse()
    print(f"[*] Parsed {len(events)} events")

    print("[*] Running anomaly detection...")
    detector = AnomalyDetector(brute_force_threshold=args.threshold)
    findings = detector.analyze(events)
    print(f"[*] Detected {len(findings)} findings")

    print(f"[*] Generating {args.format.upper()} report...")
    reporter = ReportGenerator(events, findings, out_dir)
    report_path = reporter.generate(fmt=args.format)
    print(f"[+] Report written to: {report_path}")

    # Exit code 2 if any critical findings — useful as a CI/CD gate
    has_critical = any(f.severity == "CRITICAL" for f in findings)
    return 2 if has_critical else 0


if __name__ == "__main__":
    sys.exit(main())
