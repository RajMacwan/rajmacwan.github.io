#!/usr/bin/env python3
"""
build_manifest.py
Scans site/blog/*.html, extracts title + meta + grid-pill, and writes
site/automation/post_manifest.json.
The manifest feeds the weekly featured rotation.
"""
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLOG = ROOT / "blog"
OUT = Path(__file__).resolve().parent / "post_manifest.json"

GRID_LABELS = {
    "grid-pill-dark": "DarkGrid",
    "grid-pill-threat": "ThreatGrid",
    "grid-pill-ai": "AIGrid",
    "grid-pill-stack": "StackGrid",
    "grid-pill-leadership": "LeadershipGrid",
    "grid-pill-signal": "SignalGrid",
    "grid-pill-breach": "BreachGrid",
    "grid-pill-off": "OffGrid",
}

def extract(path: Path):
    html = path.read_text(encoding="utf-8", errors="ignore")
    t = re.search(r"<title>([^<]+)</title>", html)
    title = t.group(1).strip() if t else path.stem
    # Strip site suffix
    title = re.sub(r"\s*[—\-–|]\s*(?:Raj Macwan|MacwanGrid).*$", "", title).strip()

    # Find first <h1> inside article as fallback headline
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL)
    if h1:
        headline = re.sub(r"<[^>]+>", "", h1.group(1)).strip()
        if headline:
            title = headline

    # Find grid pill class
    g = re.search(r'grid-pill grid-pill-(\w+)', html)
    pill_key = f"grid-pill-{g.group(1)}" if g else "grid-pill-signal"
    grid_label = GRID_LABELS.get(pill_key, "SignalGrid")

    # Pull first paragraph of prose as summary
    p = re.search(r"<p[^>]*>(.*?)</p>", html, re.DOTALL)
    summary = ""
    if p:
        summary = re.sub(r"<[^>]+>", "", p.group(1)).strip()
        summary = re.sub(r"\s+", " ", summary)
        if len(summary) > 240:
            summary = summary[:237].rstrip() + "..."

    # Date — try <time> tag, else fallback to file mtime
    d = re.search(r'<time[^>]*datetime="([^"]+)"', html)
    if d:
        date = d.group(1)[:10]
    else:
        date = ""

    return {
        "slug": path.stem,
        "url": f"blog/{path.name}",
        "title": title,
        "summary": summary,
        "pill_class": pill_key,
        "grid": grid_label,
        "date": date,
    }

def main():
    posts = []
    for f in sorted(BLOG.glob("*.html")):
        if f.name in ("index.html",):
            continue
        try:
            posts.append(extract(f))
        except Exception as e:
            print(f"[warn] {f.name}: {e}")
    OUT.write_text(json.dumps(posts, indent=2), encoding="utf-8")
    print(f"Wrote {len(posts)} posts -> {OUT}")

if __name__ == "__main__":
    main()
