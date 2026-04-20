#!/usr/bin/env python3
"""
weekly_patch.py
Pulls CISA KEV additions from the past 7 days and auto-generates a
"Week of YYYY-MM-DD · Vendor Digest" accordion entry summarizing what
was added. Raj then manually polishes with prose and priority calls.
"""
import datetime as dt
import json
import re
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATCH = ROOT / "patch-grid.html"
KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
START = "<!-- PATCH_LOG_START -->"

VENDOR_EMOJI = {
    "microsoft": "🪟", "apple": "🍎", "google": "🤖", "mozilla": "🦊",
    "vmware": "☁️", "cisco": "🏢", "fortinet": "🏢", "palo alto": "🏢",
    "ubuntu": "🐧", "linux": "🐧", "okta": "🔑", "cloudflare": "🔑",
}

def fetch_kev():
    try:
        req = urllib.request.Request(KEV_URL, headers={"User-Agent": "macwangrid-bot/1.0"})
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"[warn] KEV fetch failed: {e}")
        return None

def vendor_emoji(vendor: str) -> str:
    v = (vendor or "").lower()
    for k, e in VENDOR_EMOJI.items():
        if k in v:
            return e
    return "🧩"

def main():
    if not PATCH.exists():
        print("[skip] patch-grid.html missing.")
        return

    today = dt.date.today()
    monday = today - dt.timedelta(days=today.weekday())
    key = f"Week of {monday.isoformat()} · KEV digest"

    html = PATCH.read_text(encoding="utf-8")
    if key in html:
        print(f"[skip] Entry for {key} already present.")
        return

    kev = fetch_kev()
    new_entries = []
    by_vendor = defaultdict(list)
    if kev:
        cutoff = monday - dt.timedelta(days=7)  # include last full week
        for v in kev.get("vulnerabilities", []):
            da = v.get("dateAdded", "")
            try:
                when = dt.date.fromisoformat(da)
            except ValueError:
                continue
            if when >= cutoff:
                by_vendor[v.get("vendorProject", "Unknown")].append(v)

    if not by_vendor:
        body = '<p style="color: var(--text-muted); font-style: italic;">Quiet week on the KEV feed. No new entries the past 7 days — good time to clear your standing patch backlog.</p>'
    else:
        rows = []
        for vendor, vulns in sorted(by_vendor.items(), key=lambda x: -len(x[1])):
            vemoji = vendor_emoji(vendor)
            cves = ", ".join(f"<code>{v.get('cveID')}</code>" for v in vulns[:5])
            rows.append(f'<div class="fact-row"><span class="fact-key">{vemoji} {vendor}</span><span class="fact-val">{len(vulns)} new KEV · {cves}</span></div>')
        body = "\n".join(rows)
        body += '\n<h4>Patch-priority call</h4>\n<p style="color: var(--text-muted); font-style: italic;">Auto-generated from CISA KEV. Raj will annotate with priority tiers and notes after review.</p>'

    placeholder = f'''
                <details class="accordion">
                    <summary>
                        <span class="accordion-header-label">📡 {key}</span>
                        <span class="accordion-header-meta">auto-scaffold</span>
                    </summary>
                    <div class="accordion-body">
                        {body}
                    </div>
                </details>
'''

    idx = html.find(START)
    if idx == -1:
        print("[error] PATCH_LOG_START marker not found.")
        return
    insert_at = idx + len(START) + 1
    new_html = html[:insert_at] + "            " + placeholder.lstrip() + html[insert_at:]
    PATCH.write_text(new_html, encoding="utf-8")
    print(f"Added scaffold for {key} · {sum(len(v) for v in by_vendor.values())} KEV entries across {len(by_vendor)} vendors")

if __name__ == "__main__":
    main()
