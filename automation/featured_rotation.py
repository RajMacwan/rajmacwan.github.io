#!/usr/bin/env python3
"""
featured_rotation.py
Picks one post from post_manifest.json and injects it between
<!-- FEATURED_WEEK_START --> and <!-- FEATURED_WEEK_END --> in site/index.html.

Rotation strategy:
  - Deterministic by ISO week number so the same week always picks the
    same post (no drift if the workflow runs twice).
  - Skips any post already shown in the last N weeks (kept in state.json).
"""
import json
import re
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUTO = Path(__file__).resolve().parent
MANIFEST = AUTO / "post_manifest.json"
STATE = AUTO / "featured_state.json"
INDEX = ROOT / "index.html"

HISTORY_WINDOW = 8  # weeks before a post can be featured again

MARK_START = "<!-- FEATURED_WEEK_START -->"
MARK_END = "<!-- FEATURED_WEEK_END -->"

def load_manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))

def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"history": []}

def save_state(state):
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")

def pick_post(posts, state):
    recent = set(state.get("history", [])[-HISTORY_WINDOW:])
    eligible = [p for p in posts if p["slug"] not in recent]
    if not eligible:
        eligible = posts[:]
    # Deterministic by ISO year+week
    iso = dt.date.today().isocalendar()
    seed = iso.year * 100 + iso.week
    return eligible[seed % len(eligible)]

def render(post):
    title = post["title"].replace("&", "&amp;")
    summary = post["summary"].replace("&", "&amp;")
    return f'''{MARK_START}
            <a href="{post['url']}" class="featured-week-card">
                <div class="featured-week-meta">
                    <span class="grid-pill {post['pill_class']}">{post['grid']}</span>
                    <span class="featured-week-badge">★ FEATURED</span>
                </div>
                <h3>{title}</h3>
                <p>{summary}</p>
                <span class="featured-week-cta">Read →</span>
            </a>
            {MARK_END}'''

def inject(rendered):
    html = INDEX.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(MARK_START) + r".*?" + re.escape(MARK_END), re.DOTALL)
    new = pattern.sub(rendered, html)
    INDEX.write_text(new, encoding="utf-8")

def main():
    posts = load_manifest()
    state = load_state()
    chosen = pick_post(posts, state)
    inject(render(chosen))
    state.setdefault("history", []).append(chosen["slug"])
    state["history"] = state["history"][-HISTORY_WINDOW * 2:]
    state["last_run"] = dt.datetime.utcnow().isoformat() + "Z"
    state["last_slug"] = chosen["slug"]
    save_state(state)
    print(f"Featured: {chosen['slug']} ({chosen['grid']})")

if __name__ == "__main__":
    main()
