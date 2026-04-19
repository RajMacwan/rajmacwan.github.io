#!/usr/bin/env python3
"""
today_ticker.py
Generates the "Today in Security" widget injected between
<!-- TODAY_WIDGET_START --> and <!-- TODAY_WIDGET_END -->.

Sources:
  - CISA KEV JSON feed (top 3 most-recently-added vulns)
  - cyber_calendar.json (curated on-this-day events)

Fails soft: if the CISA feed is unreachable, the calendar alone is used.
"""
import json
import datetime as dt
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUTO = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"
CAL = AUTO / "cyber_calendar.json"

KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
MARK_START = "<!-- TODAY_WIDGET_START -->"
MARK_END = "<!-- TODAY_WIDGET_END -->"

def fetch_kev():
    try:
        req = urllib.request.Request(KEV_URL, headers={"User-Agent": "macwangrid-bot/1.0"})
        with urllib.request.urlopen(req, timeout=25) as r:
            data = json.loads(r.read())
        vulns = sorted(
            data.get("vulnerabilities", []),
            key=lambda v: v.get("dateAdded", ""),
            reverse=True,
        )
        return vulns[:3]
    except Exception as e:
        print(f"[warn] KEV fetch failed: {e}")
        return []

def today_calendar():
    if not CAL.exists():
        return None
    try:
        events = json.loads(CAL.read_text(encoding="utf-8"))
    except Exception:
        return None
    key = dt.date.today().strftime("%m-%d")
    return events.get(key)

def render(kev, cal):
    today = dt.date.today()
    date_str = today.strftime("%A · %B %-d, %Y") if hasattr(today, "strftime") else str(today)
    # Windows-safe formatting fallback
    try:
        date_str = today.strftime("%A · %B %-d, %Y")
    except ValueError:
        date_str = today.strftime("%A · %B %d, %Y").replace(" 0", " ")

    iso = today.isoformat()

    headline = "Quiet on the wire — no new KEV entries."
    body_lines = []

    if cal:
        headline = cal.get("title", headline)
        body_lines.append(f"<strong>On this day:</strong> {cal.get('note','')}")

    if kev:
        if not cal:
            headline = f"{len(kev)} new Known Exploited Vulnerabilities flagged by CISA."
        body_lines.append("<strong>CISA KEV · newest additions:</strong>")
        lis = []
        for v in kev:
            cve = v.get("cveID", "CVE-?")
            vendor = v.get("vendorProject", "")
            product = v.get("product", "")
            vuln = v.get("vulnerabilityName", "")
            added = v.get("dateAdded", "")
            lis.append(
                f"<li><code>{cve}</code> — {vendor} {product}: {vuln} "
                f"<span style='color:var(--text-muted);font-size:.85em'>(added {added})</span></li>"
            )
        body_lines.append("<ul>" + "".join(lis) + "</ul>")
    else:
        body_lines.append(
            "CISA's KEV feed returned no new entries in the last window. "
            "A calm day is still a good day to revisit your patch backlog."
        )

    body_html = "\n                    ".join(f"<p>{l}</p>" if not l.startswith('<') or l.startswith('<strong') else l for l in body_lines)

    return f'''{MARK_START}
                <div class="today-card">
                    <div class="today-date" id="today-date">{date_str}</div>
                    <h3 class="today-headline">{headline}</h3>
                    <div class="today-body">
                    {body_html}
                    </div>
                    <div class="today-meta">
                        <span class="today-tag">AUTO</span>
                        <span class="today-source">Generated {iso} · CISA KEV + internal calendar</span>
                    </div>
                </div>
                {MARK_END}'''

def inject(rendered):
    html = INDEX.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(MARK_START) + r".*?" + re.escape(MARK_END), re.DOTALL)
    new = pattern.sub(rendered, html)
    INDEX.write_text(new, encoding="utf-8")

def main():
    kev = fetch_kev()
    cal = today_calendar()
    inject(render(kev, cal))
    print(f"Today widget updated. KEV items: {len(kev)}, calendar hit: {bool(cal)}")

if __name__ == "__main__":
    main()
