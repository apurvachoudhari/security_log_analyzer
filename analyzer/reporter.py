"""
ReportGenerator — renders analysis results in text, JSON, or HTML format.
"""

import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from .models import Finding, LogEvent

_SEVERITY_EMOJI = {
    "CRITICAL": "🔴",
    "HIGH":     "🟠",
    "MEDIUM":   "🟡",
    "LOW":      "🔵",
    "INFO":     "⚪",
}

_SEVERITY_COLOR = {
    "CRITICAL": "#ef4444",
    "HIGH":     "#f97316",
    "MEDIUM":   "#eab308",
    "LOW":      "#3b82f6",
    "INFO":     "#6b7280",
}


class ReportGenerator:
    def __init__(
        self,
        events: list[LogEvent],
        findings: list[Finding],
        out_dir: Path,
    ) -> None:
        self.events = events
        self.findings = findings
        self.out_dir = out_dir
        self._generated_at = datetime.now()

    # ── Public API ─────────────────────────────────────────────────────────────

    def generate(self, fmt: str = "text") -> Path:
        if fmt == "json":
            return self._write_json()
        if fmt == "html":
            return self._write_html()
        return self._write_text()

    # ── Text ───────────────────────────────────────────────────────────────────

    def _write_text(self) -> Path:
        lines = [
            "=" * 70,
            "  SECURITY LOG ANALYSIS REPORT",
            f"  Generated: {self._generated_at:%Y-%m-%d %H:%M:%S}",
            "=" * 70,
            "",
            "── SUMMARY ──────────────────────────────────────────────────────────",
            f"  Total events parsed : {len(self.events)}",
            f"  Total findings      : {len(self.findings)}",
            f"  Unique source IPs   : {len({e.source_ip for e in self.events})}",
        ]
        for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"):
            count = sum(1 for f in self.findings if f.severity == sev)
            if count:
                lines.append(f"  {_SEVERITY_EMOJI[sev]} {sev:<10}: {count}")

        lines += ["", "── FINDINGS ─────────────────────────────────────────────────────────"]
        if not self.findings:
            lines.append("  No anomalies detected.")
        else:
            for i, f in enumerate(self.findings, start=1):
                lines += [
                    "",
                    f"  [{i}] {_SEVERITY_EMOJI[f.severity]} [{f.severity}] {f.title}",
                    f"      {f.description}",
                    f"      Source IP : {f.source_ip or 'N/A'}",
                    f"      User      : {f.affected_user or 'N/A'}",
                    f"      Events    : {f.event_count}",
                    f"      Window    : {f.first_seen:%H:%M:%S} – {f.last_seen:%H:%M:%S}",
                ]
                if f.evidence:
                    lines.append("      Evidence  :")
                    for ev in f.evidence[:3]:
                        lines.append(f"        > {ev[:120]}")

        lines += [
            "",
            "── TOP SOURCE IPs ───────────────────────────────────────────────────",
        ]
        ip_counts = Counter(e.source_ip for e in self.events)
        for ip, count in ip_counts.most_common(10):
            lines.append(f"  {ip:<20} {count} events")

        lines += ["", "=" * 70, "  END OF REPORT", "=" * 70]

        path = self.out_dir / f"report_{self._ts()}.txt"
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    # ── JSON ───────────────────────────────────────────────────────────────────

    def _write_json(self) -> Path:
        ip_counts = Counter(e.source_ip for e in self.events)
        event_type_counts = Counter(e.event_type for e in self.events)

        payload = {
            "generated_at": self._generated_at.isoformat(),
            "summary": {
                "total_events": len(self.events),
                "total_findings": len(self.findings),
                "unique_ips": len({e.source_ip for e in self.events}),
                "severity_breakdown": {
                    sev: sum(1 for f in self.findings if f.severity == sev)
                    for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")
                },
                "event_type_breakdown": dict(event_type_counts.most_common()),
                "top_source_ips": dict(ip_counts.most_common(10)),
            },
            "findings": [
                {
                    "title": f.title,
                    "severity": f.severity,
                    "description": f.description,
                    "source_ip": f.source_ip,
                    "affected_user": f.affected_user,
                    "event_count": f.event_count,
                    "first_seen": f.first_seen.isoformat(),
                    "last_seen": f.last_seen.isoformat(),
                    "duration_seconds": round(f.duration_seconds, 1),
                    "evidence": f.evidence,
                }
                for f in self.findings
            ],
        }

        path = self.out_dir / f"report_{self._ts()}.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    # ── HTML ───────────────────────────────────────────────────────────────────

    def _write_html(self) -> Path:
        ip_counts = Counter(e.source_ip for e in self.events)
        event_type_counts = Counter(e.event_type for e in self.events)
        sev_counts = {
            sev: sum(1 for f in self.findings if f.severity == sev)
            for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW")
        }

        finding_cards = ""
        for f in self.findings:
            color = _SEVERITY_COLOR.get(f.severity, "#6b7280")
            evidence_html = "".join(
                f'<div class="evidence-line">{ev[:160]}</div>'
                for ev in f.evidence[:3]
            )
            finding_cards += f"""
            <div class="finding-card" style="border-left: 4px solid {color}">
              <div class="finding-header">
                <span class="sev-badge" style="background:{color}22; color:{color}; border:1px solid {color}44">
                  {f.severity}
                </span>
                <span class="finding-title">{f.title}</span>
              </div>
              <p class="finding-desc">{f.description}</p>
              <div class="finding-meta">
                <span>🌐 {f.source_ip or 'N/A'}</span>
                <span>👤 {f.affected_user or 'N/A'}</span>
                <span>📊 {f.event_count} events</span>
                <span>🕐 {f.first_seen:%H:%M:%S} – {f.last_seen:%H:%M:%S}</span>
              </div>
              {"<div class='evidence'>" + evidence_html + "</div>" if f.evidence else ""}
            </div>"""

        ip_rows = "".join(
            f"<tr><td>{ip}</td><td>{cnt}</td></tr>"
            for ip, cnt in ip_counts.most_common(10)
        )
        type_rows = "".join(
            f"<tr><td>{t}</td><td>{cnt}</td></tr>"
            for t, cnt in event_type_counts.most_common(10)
        )

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Security Log Analysis Report</title>
<style>
  :root {{
    --bg: #0f172a; --surface: #1e293b; --surface2: #263045;
    --border: #334155; --text: #e2e8f0; --muted: #94a3b8;
    --accent: #38bdf8; --font: 'Segoe UI', system-ui, sans-serif;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: var(--font); padding: 32px 16px; }}
  .container {{ max-width: 960px; margin: 0 auto; }}
  h1 {{ font-size: 24px; font-weight: 800; color: #fff; margin-bottom: 4px; }}
  .subtitle {{ color: var(--muted); font-size: 13px; margin-bottom: 32px; }}
  .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 32px; }}
  .stat-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; text-align: center; }}
  .stat-value {{ font-size: 28px; font-weight: 800; color: var(--accent); }}
  .stat-label {{ font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; margin-top: 4px; }}
  .sev-card {{ background: var(--surface); border-radius: 8px; padding: 16px; text-align: center; border: 1px solid; }}
  h2 {{ font-size: 16px; font-weight: 700; color: #fff; margin: 28px 0 14px; border-bottom: 1px solid var(--border); padding-bottom: 8px; }}
  .finding-card {{ background: var(--surface); border-radius: 8px; padding: 18px; margin-bottom: 12px; }}
  .finding-header {{ display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }}
  .sev-badge {{ font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 4px; letter-spacing: 0.06em; }}
  .finding-title {{ font-weight: 700; font-size: 15px; color: #fff; }}
  .finding-desc {{ font-size: 13px; color: var(--muted); margin-bottom: 10px; line-height: 1.6; }}
  .finding-meta {{ display: flex; gap: 16px; flex-wrap: wrap; font-size: 12px; color: var(--muted); }}
  .evidence {{ background: #0a0f1e; border-radius: 4px; padding: 10px 12px; margin-top: 10px; }}
  .evidence-line {{ font-family: monospace; font-size: 11px; color: #94a3b8; padding: 2px 0; word-break: break-all; }}
  table {{ width: 100%; border-collapse: collapse; background: var(--surface); border-radius: 8px; overflow: hidden; }}
  th {{ background: var(--surface2); font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); padding: 10px 14px; text-align: left; }}
  td {{ padding: 9px 14px; font-size: 13px; border-top: 1px solid var(--border); }}
  .tables-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  @media (max-width: 600px) {{ .tables-grid {{ grid-template-columns: 1fr; }} }}
  footer {{ text-align: center; color: var(--muted); font-size: 11px; margin-top: 48px; }}
</style>
</head>
<body>
<div class="container">
  <h1>🛡️ Security Log Analysis Report</h1>
  <p class="subtitle">Generated: {self._generated_at:%Y-%m-%d %H:%M:%S} &nbsp;·&nbsp; {len(self.events)} events parsed &nbsp;·&nbsp; {len(self.findings)} findings</p>

  <div class="summary-grid">
    <div class="stat-card"><div class="stat-value">{len(self.events)}</div><div class="stat-label">Events</div></div>
    <div class="stat-card"><div class="stat-value">{len(self.findings)}</div><div class="stat-label">Findings</div></div>
    <div class="stat-card"><div class="stat-value">{len({e.source_ip for e in self.events})}</div><div class="stat-label">Unique IPs</div></div>
    <div class="sev-card" style="color:#ef4444; border-color:#ef444444"><div class="stat-value" style="color:#ef4444">{sev_counts['CRITICAL']}</div><div class="stat-label">Critical</div></div>
    <div class="sev-card" style="color:#f97316; border-color:#f9731644"><div class="stat-value" style="color:#f97316">{sev_counts['HIGH']}</div><div class="stat-label">High</div></div>
    <div class="sev-card" style="color:#eab308; border-color:#eab30844"><div class="stat-value" style="color:#eab308">{sev_counts['MEDIUM']}</div><div class="stat-label">Medium</div></div>
  </div>

  <h2>Findings</h2>
  {finding_cards if finding_cards else '<p style="color:var(--muted)">No anomalies detected.</p>'}

  <h2>Intelligence</h2>
  <div class="tables-grid">
    <div>
      <table>
        <thead><tr><th>Source IP</th><th>Events</th></tr></thead>
        <tbody>{ip_rows}</tbody>
      </table>
    </div>
    <div>
      <table>
        <thead><tr><th>Event Type</th><th>Count</th></tr></thead>
        <tbody>{type_rows}</tbody>
      </table>
    </div>
  </div>
  <footer>Security Log Analyzer · Apurva Choudhari</footer>
</div>
</body>
</html>"""

        path = self.out_dir / f"report_{self._ts()}.html"
        path.write_text(html, encoding="utf-8")
        return path

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _ts(self) -> str:
        return self._generated_at.strftime("%Y%m%d_%H%M%S")
