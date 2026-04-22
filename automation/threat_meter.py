#!/usr/bin/env python3
"""
threat_meter.py
Computes current threat level from CISA KEV and injects the meter into
index.html (between <!-- THREAT_METER_START/END -->) and breached-grid.html
(between <!-- BREACHED_METER_START/END -->).

Level formula (simple, explainable, tunable):
  score = min(10, kev_adds_7d // 2 + active_zero_days * 2)
  0-1  : GREEN   (calm)
  2-3  : BLUE    (elevated)
  4-5  : YELLOW  (heightened)
  6-7  : ORANGE  (high)
  8+   : RED     (critical)

Exposed as JSON at automation/threat_state.json for auditability.
"""
import json
import datetime as dt
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUTO = Path(__file__).resolve().parent
STATE = AUTO / "threat_state.json"
INDEX = ROOT / "index.html"
WIRE = ROOT / "breached-grid.html"

KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"

LEVELS = [
    (0, "GREEN",   "Calm across the wire.",     "Background-noise KEV adds. No active-exploitation surges."),
    (2, "BLUE",    "Elevated but steady.",      "Normal breach cadence. Routine patch discipline sufficient."),
    (4, "YELLOW",  "Heightened activity.",      "Above-average KEV adds this week. Watch your management-plane exposure."),
    (6, "ORANGE",  "High — active campaigns.",  "Exploitation campaigns underway. Validate patch status on internet-facing assets."),
    (8, "RED",     "Critical — surge in progress.", "Pronounced uptick in active exploitation. Treat patch windows as incident response."),
]

def fetch_kev():
    try:
        req = urllib.request.Request(KEV_URL, headers={"User-Agent": "macwangrid-bot/1.0"})
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"[warn] KEV fetch failed: {e}")
        return None

def compute(kev):
    if not kev:
        # Fail-soft: show BLUE/elevated if we can't reach the source
        return 2, "BLUE", "Data source unreachable — showing conservative default.", "CISA KEV feed did not respond. Threat level defaults to ELEVATED until refreshed.", {"kev_adds_7d": None, "active_zero_days": None}

    today = dt.date.today()
    cutoff = today - dt.timedelta(days=7)
    adds_7d = 0
    zero_days = 0
    for v in kev.get("vulnerabilities", []):
        da = v.get("dateAdded", "")
        try:
            when = dt.date.fromisoformat(da)
        except ValueError:
            continue
        if when >= cutoff:
            adds_7d += 1
            # Heuristic: KEVs with dueDate within 14 days of release = high urgency
            if v.get("knownRansomwareCampaignUse", "").lower() == "known":
                zero_days += 1

    score = min(10, adds_7d // 2 + zero_days * 2)

    label, headline, body = LEVELS[0][1], LEVELS[0][2], LEVELS[0][3]
    for threshold, lab, head, bd in LEVELS:
        if score >= threshold:
            label, headline, body = lab, head, bd
    return score, label, headline, body, {"kev_adds_7d": adds_7d, "active_zero_days": zero_days}

def render(level, headline, body, meta, small_source):
    slug = level.lower()
    return f'''<a href="breached-grid.html" class="threat-meter meter-level-{slug}" id="threat-meter" title="Current threat level — click for live breach intel">
                <div class="meter-info">
                    <div class="meter-level">Threat Level</div>
                    <div class="meter-label">{level}</div>
                </div>
                <div class="meter-gauge">
                    <span class="meter-seg"></span>
                    <span class="meter-seg"></span>
                    <span class="meter-seg"></span>
                    <span class="meter-seg"></span>
                    <span class="meter-seg"></span>
                </div>
                <div class="meter-text">
                    <strong>{headline}</strong>
                    <small>{body} · KEV adds 7d: {meta.get("kev_adds_7d","?")} · ransomware-linked: {meta.get("active_zero_days","?")} · updated {dt.date.today().isoformat()}</small>
                </div>
            </a>'''

def inject(path: Path, start_marker: str, end_marker: str, rendered: str, wrapper_classes_strip=False):
    html = path.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(start_marker) + r".*?" + re.escape(end_marker), re.DOTALL)
    replacement = f"{start_marker}\n            {rendered}\n            {end_marker}"
    new = pattern.sub(replacement, html)
    path.write_text(new, encoding="utf-8")

def main():
    kev = fetch_kev()
    score, level, headline, body, meta = compute(kev)
    rendered = render(level, headline, body, meta, "CISA KEV feed")

    if INDEX.exists():
        inject(INDEX, "<!-- THREAT_METER_START -->", "<!-- THREAT_METER_END -->", rendered)
    if WIRE.exists():
        # Wire meter uses its own markers; replace with the same rendered block but with static (non-link) behavior
        wire_rendered = rendered.replace('href="breached-grid.html"', 'href="#"').replace('id="threat-meter"', 'style="cursor: default;"')
        inject(WIRE, "<!-- BREACHED_METER_START -->", "<!-- BREACHED_METER_END -->", wire_rendered)

    STATE.write_text(json.dumps({
        "level": level,
        "score": score,
        "headline": headline,
        "body": body,
        "meta": meta,
        "updated": dt.datetime.utcnow().isoformat() + "Z",
    }, indent=2), encoding="utf-8")

    print(f"Threat meter: {level} (score {score}) — {headline}")

if __name__ == "__main__":
    main()
