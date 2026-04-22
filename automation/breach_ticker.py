#!/usr/bin/env python3
"""
breach_ticker.py
Daily-refreshed ticker of confirmed public breaches on BreachedGrid.

Pulls from two independent clearnet sources (no onion, no leak sites):
  - Have I Been Pwned — public /api/v3/breaches endpoint
  - BleepingComputer — main RSS feed, filtered for breach-related items

Writes a rendered HTML block into breached-grid.html between
<!-- BREACH_TICKER_START --> and <!-- BREACH_TICKER_END -->.

stdlib-only, CSP-safe, fails soft if a source is unreachable.
"""
import json
import re
import datetime as dt
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT  = Path(__file__).resolve().parent.parent
AUTO  = Path(__file__).resolve().parent
PAGE  = ROOT / "breached-grid.html"
STATE = AUTO / "breach_ticker_state.json"

HIBP_URL     = "https://haveibeenpwned.com/api/v3/breaches"
BLEEPING_RSS = "https://www.bleepingcomputer.com/feed/"

USER_AGENT = "macwangrid-bot/1.0 (+https://macwangrid.com)"

START_MARKER = "<!-- BREACH_TICKER_START -->"
END_MARKER   = "<!-- BREACH_TICKER_END -->"

DAYS_WINDOW = 14
MAX_ROWS    = 12


def fetch(url, accept="application/json"):
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": accept,
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def fetch_hibp():
    try:
        data = json.loads(fetch(HIBP_URL, accept="application/json"))
    except Exception as e:
        print(f"[warn] HIBP fetch failed: {e}")
        return []
    cutoff = dt.date.today() - dt.timedelta(days=DAYS_WINDOW)
    out = []
    for b in data:
        try:
            added = dt.date.fromisoformat((b.get("AddedDate") or "")[:10])
        except ValueError:
            continue
        if added < cutoff:
            continue
        out.append({
            "source":  "HIBP",
            "name":    b.get("Title") or b.get("Name") or "Unknown",
            "domain":  b.get("Domain") or "",
            "records": int(b.get("PwnCount") or 0),
            "date":    (b.get("BreachDate") or "")[:10],
            "added":   (b.get("AddedDate")  or "")[:10],
            "url":     f"https://haveibeenpwned.com/PwnedWebsites#{b.get('Name','')}",
        })
    out.sort(key=lambda x: x["added"], reverse=True)
    return out


def fetch_bleeping():
    try:
        xml = fetch(BLEEPING_RSS, accept="application/rss+xml, application/xml")
    except Exception as e:
        print(f"[warn] BleepingComputer fetch failed: {e}")
        return []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        print(f"[warn] RSS parse failed: {e}")
        return []
    cutoff = dt.datetime.utcnow() - dt.timedelta(days=DAYS_WINDOW)
    breach_kw = re.compile(
        r"\b(breach|breached|data breach|leak|leaked|exposed|hack(ed|er)?|"
        r"ransomware|stolen|extorti|compromise[ds]?|exfiltrat)",
        re.IGNORECASE,
    )
    items = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if not breach_kw.search(title):
            continue
        link = (item.findtext("link") or "").strip()
        pub  = item.findtext("pubDate") or ""
        try:
            when = dt.datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %z")
            when = when.replace(tzinfo=None)
        except Exception:
            when = dt.datetime.utcnow()
        if when < cutoff:
            continue
        items.append({
            "source": "BleepingComputer",
            "name":   title,
            "url":    link,
            "added":  when.strftime("%Y-%m-%d"),
        })
    return items


def fmt_records(n):
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M records"
    if n >= 1_000:
        return f"{n/1_000:.0f}K records"
    if n:
        return f"{n} records"
    return "—"


def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def row_hibp(b):
    return (
        f'<a href="{esc(b["url"])}" target="_blank" rel="noopener" class="ticker-row ticker-hibp">'
        f'<span class="ticker-src ticker-src-hibp">HIBP</span>'
        f'<span class="ticker-name">{esc(b["name"])}</span>'
        f'<span class="ticker-meta">{fmt_records(b["records"])} · added {b["added"]}</span>'
        f'</a>'
    )


def row_bc(b):
    return (
        f'<a href="{esc(b["url"])}" target="_blank" rel="noopener" class="ticker-row ticker-bc">'
        f'<span class="ticker-src ticker-src-bc">BC</span>'
        f'<span class="ticker-name">{esc(b["name"])}</span>'
        f'<span class="ticker-meta">{b["added"]}</span>'
        f'</a>'
    )


def render(hibp, bc):
    today = dt.date.today().isoformat()
    combined = [("hibp", h) for h in hibp] + [("bc", b) for b in bc]
    combined.sort(key=lambda x: x[1].get("added", ""), reverse=True)

    if not combined:
        body = (
            '<p class="ticker-empty">'
            'No confirmed breach disclosures in the past 14 days on either feed. '
            'Calm week — use it.'
            '</p>'
        )
    else:
        rendered = []
        for typ, b in combined[:MAX_ROWS]:
            rendered.append(row_hibp(b) if typ == "hibp" else row_bc(b))
        body = "\n        ".join(rendered)

    return f'''<div class="breach-ticker">
    <div class="ticker-header">
        <span class="ticker-dot"></span>
        <h3>Across the wire · past 14 days</h3>
        <span class="ticker-updated">updated {today}</span>
    </div>
    <div class="ticker-list">
        {body}
    </div>
    <p class="ticker-note">
        Auto-refreshed daily from public sources:
        <a href="https://haveibeenpwned.com/" target="_blank" rel="noopener">Have I Been Pwned</a>
        and
        <a href="https://www.bleepingcomputer.com/" target="_blank" rel="noopener">BleepingComputer</a>.
        No content mirrored from the dark web — clearnet public disclosures only.
    </p>
</div>'''


def inject(block):
    if not PAGE.exists():
        print(f"[error] {PAGE} not found")
        return False
    page = PAGE.read_text(encoding="utf-8")
    pat = re.compile(re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER), re.DOTALL)
    if not pat.search(page):
        print(f"[error] {START_MARKER}/{END_MARKER} markers missing in {PAGE.name}")
        return False
    new_page = pat.sub(f"{START_MARKER}\n{block}\n{END_MARKER}", page)
    PAGE.write_text(new_page, encoding="utf-8")
    return True


def main():
    hibp = fetch_hibp()
    bc   = fetch_bleeping()
    block = render(hibp, bc)
    ok = inject(block)
    STATE.write_text(json.dumps({
        "updated": dt.datetime.utcnow().isoformat() + "Z",
        "hibp_count": len(hibp),
        "bc_count":   len(bc),
        "injected":   ok,
    }, indent=2), encoding="utf-8")
    print(f"Breach ticker: HIBP={len(hibp)}  BleepingComputer={len(bc)}  injected={ok}")


if __name__ == "__main__":
    main()
