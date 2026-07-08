#!/usr/bin/env python3
"""
weekly_grid_publisher.py

Publishes one queued post per week, rotating through five grids:
    Threat -> Infra -> Dark -> AI -> Intel  (each grid every 5 weeks)

Rotation is deterministic from the date: the grid for a given week is
ROTATION[weeks_since_epoch % 5], epoch = the first publish Tuesday.
No state file — a missed or re-run week self-corrects.

Each run:
  1. Decide today's grid from the rotation.
  2. Pick the next draft in drafts/queue/<grid>/*.html. Drafts publish in
     filename order, so prefix them NN- (e.g. 01-, 02-) to set the order;
     the prefix is stripped from the published slug/URL. Unprefixed drafts
     are fine too (they just sort by name).
     (If the queue is empty, log and exit 0 — nothing to publish.)
  3. Promote it to blog/<slug>.html, stamping the publish date and read time.
  4. Insert a card into <grid>-grid.html and into blog/index.html.
  5. Insert an item into blog/feed.xml and a URL into sitemap.xml.
  6. Rebuild automation/post_manifest.json.

Committing/pushing is done by the calling GitHub Actions workflow.

Timing:
  The workflow triggers at 15:00 and 16:00 UTC on Tuesdays so that exactly
  one of them lands at 11:00 America/New_York year-round (EDT=15:00Z,
  EST=16:00Z). This script only proceeds when the local Eastern time is
  11:00 on a Tuesday, unless FORCE_PUBLISH=1 (manual/testing) is set.
  PUBLISH_DATE_OVERRIDE=YYYY-MM-DD forces a specific publish date (testing).
"""
import datetime as dt
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
AUTO = Path(__file__).resolve().parent
BLOG = ROOT / "blog"
QUEUE = ROOT / "drafts" / "queue"

ET = ZoneInfo("America/New_York")

# Rotation order and per-grid presentation metadata.
ROTATION = ["threat", "infra", "dark", "ai", "intel"]
GRID_META = {
    "threat": ("grid-pill-threat", "ThreatGrid"),
    "infra":  ("grid-pill-infra",  "InfraGrid"),
    "dark":   ("grid-pill-dark",   "DarkGrid"),
    "ai":     ("grid-pill-ai",     "AIGrid"),
    "intel":  ("grid-pill-intel",  "IntelGrid"),
}

# First scheduled publish Tuesday. Week 0 == ThreatGrid.
EPOCH = dt.date(2026, 7, 14)


def log(msg):
    print(f"[weekly-grid] {msg}", flush=True)


def publish_date():
    override = os.environ.get("PUBLISH_DATE_OVERRIDE")
    if override:
        return dt.date.fromisoformat(override)
    return dt.datetime.now(ET).date()


def time_gate_ok():
    if os.environ.get("FORCE_PUBLISH") == "1":
        return True
    now = dt.datetime.now(ET)
    # Tuesday == weekday 1; publish hour 11:00 local Eastern.
    return now.weekday() == 1 and now.hour == 11


def grid_for_date(d: dt.date) -> str:
    weeks = (d - EPOCH).days // 7
    return ROTATION[weeks % 5]


def pick_draft(grid: str):
    gdir = QUEUE / grid
    if not gdir.is_dir():
        return None
    drafts = sorted(gdir.glob("*.html"))
    return drafts[0] if drafts else None


# ---- extraction from a draft's HTML -------------------------------------

def extract_meta(html: str, slug: str):
    t = re.search(r"<title>([^<]+)</title>", html)
    title = t.group(1).strip() if t else slug
    title = re.sub(r"\s*[—\-–|]\s*(?:Raj Macwan|MacwanGrid).*$", "", title).strip()
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL)
    if h1:
        headline = re.sub(r"<[^>]+>", "", h1.group(1)).strip()
        if headline:
            title = headline

    m = re.search(r'<meta name="description" content="([^"]*)"', html)
    summary = m.group(1).strip() if m else ""

    g = re.search(r"grid-pill grid-pill-(\w+)", html)
    grid = g.group(1) if g else None
    return title, summary, grid


def read_minutes(html: str) -> int:
    body = re.search(r'<div class="article-body">(.*?)</div>\s*<hr', html, re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", body.group(1)) if body else ""
    words = len(text.split())
    return max(1, round(words / 200))


# ---- HTML/XML fragment builders -----------------------------------------

def grid_card(slug, pill, label, human, title, summary):
    return (
        f'                <a href="blog/{slug}.html" class="post-card">\n'
        f'                    <div class="post-meta">\n'
        f'                        <span class="grid-pill {pill}">{label}</span>\n'
        f'                        <span>{human}</span>\n'
        f'                    </div>\n'
        f'                    <h3>{title}</h3>\n'
        f'                    <p>{summary}</p>\n'
        f'                </a>\n'
    )


def index_card(slug, pill, label, human, title, summary):
    return (
        f'                <a href="{slug}.html" class="post-card">\n'
        f'                    <div class="post-meta">\n'
        f'                        <span class="grid-pill {pill}">{label}</span>\n'
        f'                        <span>{human}</span>\n'
        f'                    </div>\n'
        f'                    <h3>{title}</h3>\n'
        f'                    <p>{summary}</p>\n'
        f'                </a>\n'
    )


def xml_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# ---- listing mutations ---------------------------------------------------

def insert_into_grid_page(grid, card):
    path = ROOT / f"{grid}-grid.html"
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    try:
        ai = next(i for i, l in enumerate(lines) if "All Posts in This Grid" in l)
    except StopIteration:
        raise SystemExit(f"[weekly-grid] ERROR: 'All Posts in This Grid' not found in {path.name}")
    di = next(i for i in range(ai, len(lines)) if '<div class="card-grid-2">' in lines[i])
    lines.insert(di + 1, card)
    path.write_text("".join(lines), encoding="utf-8")


def insert_into_index(card):
    path = BLOG / "index.html"
    t = path.read_text(encoding="utf-8")
    anchor = '            <div class="card-grid-2">\n'
    if t.count(anchor) != 1:
        raise SystemExit("[weekly-grid] ERROR: index card-grid-2 anchor not unique/found")
    t = t.replace(anchor, anchor + card, 1)
    # bump "<N> posts across 10 grids" and "<N> articles across 10 grids"
    def bump(m):
        return str(int(m.group(1)) + 1) + m.group(2)
    t = re.sub(r"(\d+)( posts across 10 grids)", bump, t)
    t = re.sub(r"(\d+)( articles across 10 grids)", bump, t)
    path.write_text(t, encoding="utf-8")


def insert_into_feed(slug, title, summary, label, when: dt.date):
    path = BLOG / "feed.xml"
    f = path.read_text(encoding="utf-8")
    pub = dt.datetime(when.year, when.month, when.day, 15, 0, 0)
    rfc = pub.strftime("%a, %d %b %Y %H:%M:%S GMT")
    item = (
        f'    <item>\n'
        f'      <title>{xml_escape(title)}</title>\n'
        f'      <link>https://macwangrid.com/blog/{slug}.html</link>\n'
        f'      <description>{xml_escape(summary)}</description>\n'
        f'      <pubDate>{rfc}</pubDate>\n'
        f'      <guid isPermaLink="true">https://macwangrid.com/blog/{slug}.html</guid>\n'
        f'      <category>{xml_escape(label)}</category>\n'
        f'    </item>\n'
    )
    f = re.sub(r"<lastBuildDate>[^<]*</lastBuildDate>",
               f"<lastBuildDate>{rfc}</lastBuildDate>", f, count=1)
    idx = f.index("    <item>")
    f = f[:idx] + item + f[idx:]
    path.write_text(f, encoding="utf-8")


def insert_into_sitemap(slug, when: dt.date):
    path = ROOT / "sitemap.xml"
    s = path.read_text(encoding="utf-8")
    iso = when.isoformat()
    url = (f'  <url><loc>https://macwangrid.com/blog/{slug}.html</loc>'
           f'<lastmod>{iso}</lastmod><priority>0.7</priority></url>\n')
    # Bump the blog/ index lastmod and insert the new post URL right after it.
    blog_line_re = re.compile(r'(  <url><loc>https://macwangrid\.com/blog/</loc><lastmod>)[^<]*(</lastmod><priority>[^<]*</priority></url>\n)')
    def repl(mm):
        return mm.group(1) + iso + mm.group(2) + url
    s2, n = blog_line_re.subn(repl, s, count=1)
    if n == 0:
        # fall back: append before closing tag
        s2 = s.replace("</urlset>", url + "</urlset>", 1)
    path.write_text(s2, encoding="utf-8")


def rebuild_manifest():
    subprocess.check_call([sys.executable, str(AUTO / "build_manifest.py")])


# ---- main ---------------------------------------------------------------

def main():
    if not time_gate_ok():
        now = dt.datetime.now(ET)
        log(f"Not the publish window (local ET {now:%Y-%m-%d %H:%M %Z}, "
            f"weekday={now.weekday()}). Set FORCE_PUBLISH=1 to override. Exiting.")
        return

    when = publish_date()
    grid = grid_for_date(when)
    pill, label = GRID_META[grid]
    human = when.strftime("%b %d, %Y")
    iso = when.isoformat()
    log(f"Publish date {iso} -> grid '{grid}' ({label}).")

    draft = pick_draft(grid)
    if draft is None:
        log(f"Queue drafts/queue/{grid}/ is empty — nothing to publish this week. Exiting cleanly.")
        return

    slug = re.sub(r"^\d+-", "", draft.stem)  # strip NN- ordering prefix
    dest = BLOG / f"{slug}.html"
    if dest.exists():
        log(f"blog/{slug}.html already exists — skipping to avoid overwrite. "
            f"Move or rename the draft. Exiting.")
        return

    html = draft.read_text(encoding="utf-8")
    title, summary, draft_grid = extract_meta(html, slug)
    if draft_grid != grid:
        log(f"WARNING: draft grid-pill is '{draft_grid}' but rotation expects '{grid}'. "
            f"Using rotation grid for placement; check the draft.")
    minutes = read_minutes(html)

    # Stamp date + read time, then promote.
    html = html.replace("__PUBDATE_ISO__", iso).replace("__READMIN__", str(minutes))
    dest.write_text(html, encoding="utf-8")
    draft.unlink()
    log(f"Promoted -> blog/{slug}.html  (\"{title}\", {minutes} min read)")

    insert_into_grid_page(grid, grid_card(slug, pill, label, human, title, summary))
    insert_into_index(index_card(slug, pill, label, human, title, summary))
    insert_into_feed(slug, title, summary, label, when)
    insert_into_sitemap(slug, when)
    log("Updated grid page, blog index, feed.xml, sitemap.xml.")

    rebuild_manifest()
    log("Rebuilt post_manifest.json. Done.")

    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as fh:
            fh.write(f"### Weekly grid post published\n\n"
                     f"- **Grid:** {label}\n- **Post:** {title}\n"
                     f"- **URL:** https://macwangrid.com/blog/{slug}.html\n"
                     f"- **Date:** {iso}\n")


if __name__ == "__main__":
    main()
