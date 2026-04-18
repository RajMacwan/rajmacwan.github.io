#!/usr/bin/env python3
"""
rajmacwan.com - Industry Watch Aggregator
==========================================
Fetches curated IT infrastructure, cybersecurity, and AI news from public feeds.
Renders a clean professional news page - NOT the dark/hacker aesthetic.

Refreshes every 6 hours via cron.
"""

import os
import sys
import html
import json
import hashlib
import logging
import socket
from datetime import datetime, timezone, timedelta
from email.utils import formatdate
from pathlib import Path

try:
    import feedparser
except ImportError:
    print("ERROR: feedparser not installed. apt install python3-feedparser")
    sys.exit(1)

# ===========================================================================
# Configuration
# ===========================================================================

WEB_ROOT = Path("/var/www/html")
CACHE_DIR = Path("/var/lib/rajmacwan/cache")
ARTICLES_TO_SHOW = 40

# Curated feeds - a senior IT leader's reading list.
# Grouped by category for the UI.
FEEDS = [
    # Infrastructure / Cloud / Architecture
    ("AWS Architecture",      "https://aws.amazon.com/blogs/architecture/feed/",     "Infrastructure"),
    ("Microsoft Tech Community","https://techcommunity.microsoft.com/t5/s/gxcuf89792/group-rss/public/true","Infrastructure"),
    ("Google Cloud Blog",     "https://cloud.google.com/blog/rss/",                  "Infrastructure"),

    # Cybersecurity
    ("CISA Advisories",       "https://www.cisa.gov/cybersecurity-advisories/all.xml","Security"),
    ("Krebs on Security",     "https://krebsonsecurity.com/feed/",                   "Security"),
    ("The Hacker News",       "https://feeds.feedburner.com/TheHackersNews",         "Security"),
    ("BleepingComputer",      "https://www.bleepingcomputer.com/feed/",              "Security"),
    ("Schneier on Security",  "https://www.schneier.com/feed/atom/",                 "Security"),

    # AI / Automation / Data
    ("Google AI Blog",        "https://blog.google/technology/ai/rss/",              "AI"),
    ("OpenAI Blog",           "https://openai.com/blog/rss.xml",                     "AI"),
    ("MIT Tech Review AI",    "https://www.technologyreview.com/topic/artificial-intelligence/feed","AI"),

    # Industry / Practice
    ("InfoQ - Architecture",  "https://feed.infoq.com/architecture-design/articles/","Practice"),
    ("MIT Sloan Management",  "https://mitsloan.mit.edu/ideas-made-to-matter/rss.xml","Practice"),

    # Thought leaders / Analysis
    ("Ars Technica - IT",     "https://feeds.arstechnica.com/arstechnica/technology-lab","Industry"),
    ("Gartner Blog Network",  "https://blogs.gartner.com/feed/",                     "Industry"),
]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("industrywatch")


def fetch_feed(name, url, category):
    log.info("Fetching: %s", name)
    articles = []
    try:
        feed = feedparser.parse(url)
        if feed.bozo and not feed.entries:
            log.warning("  Failed: %s", feed.bozo_exception)
            return []
        for entry in feed.entries[:20]:  # cap per feed
            articles.append(parse_entry(entry, name, category))
        log.info("  Got %d articles", len(articles))
    except Exception as e:
        log.error("  Error: %s", e)
    return articles


def parse_entry(entry, source, category):
    title = entry.get("title", "Untitled")
    link = entry.get("link", "")

    description = ""
    if "summary" in entry:
        description = entry.summary
    elif "description" in entry:
        description = entry.description

    description = strip_html(description)
    if len(description) > 300:
        description = description[:297] + "..."

    published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if published_parsed:
        try:
            published = datetime(*published_parsed[:6], tzinfo=timezone.utc)
        except (ValueError, TypeError):
            published = datetime.now(timezone.utc)
    else:
        published = datetime.now(timezone.utc)

    return {
        "title": title,
        "link": link,
        "description": description,
        "published": published,
        "published_display": published.strftime("%b %d, %Y"),
        "source": source,
        "category": category,
        "uid": hashlib.md5((title + link).encode("utf-8")).hexdigest(),
    }


def strip_html(text):
    result = []
    in_tag = False
    for c in text:
        if c == "<":
            in_tag = True
        elif c == ">":
            in_tag = False
        elif not in_tag:
            result.append(c)
    return html.unescape(" ".join("".join(result).split()))


def render_page(articles, last_updated):
    """Render the industry-watch.html page."""

    # Group by category
    by_category = {}
    for a in articles:
        by_category.setdefault(a["category"], []).append(a)

    # Build news items HTML
    def render_news_item(a):
        return f"""            <article class="news-item">
                <h4><a href="{html.escape(a['link'])}" target="_blank" rel="noopener noreferrer">{html.escape(a['title'])}</a></h4>
                <div class="news-meta">
                    <span><strong>{html.escape(a['source'])}</strong></span>
                    <span>{html.escape(a['published_display'])}</span>
                </div>
                <p>{html.escape(a['description'])}</p>
            </article>
"""

    # Latest section (all articles sorted by date)
    all_sorted = sorted(articles, key=lambda a: a["published"], reverse=True)[:ARTICLES_TO_SHOW]
    latest_html = '<div class="news-list">\n'
    for a in all_sorted:
        latest_html += render_news_item(a)
    latest_html += '</div>\n'

    # By-category sections (top 8 each)
    category_html = ""
    for cat in ["Security", "Infrastructure", "AI", "Practice", "Industry"]:
        if cat not in by_category:
            continue
        items = sorted(by_category[cat], key=lambda a: a["published"], reverse=True)[:8]
        category_html += f"""
            <div class="section-heading" style="margin-top: 3rem;">
                <span class="eyebrow">{cat}</span>
                <h2>{cat} — Recent</h2>
            </div>
            <div class="news-list">
"""
        for a in items:
            category_html += render_news_item(a)
        category_html += '</div>\n'

    # Sources list
    sources_html = '<div class="card-grid" style="margin-top: 2rem;">\n'
    for name, url, cat in FEEDS:
        sources_html += f"""<div class="card">
            <div class="card-icon">📡</div>
            <h3>{html.escape(name)}</h3>
            <p><strong>{cat}</strong></p>
            <p><a href="{html.escape(url)}" target="_blank" rel="noopener noreferrer">Visit Source →</a></p>
        </div>
"""
    sources_html += '</div>\n'

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Industry Watch — Raj Macwan</title>
    <meta name="description" content="Curated industry news from trusted sources - infrastructure, cybersecurity, AI, and IT practice. Auto-refreshed every 6 hours.">
    <meta property="og:type" content="website">
    <meta property="og:title" content="Industry Watch — Raj Macwan">
    <meta property="og:description" content="Curated infrastructure, security, and AI news, auto-refreshed every 6 hours.">
    <link rel="stylesheet" href="style.css">
    <link rel="canonical" href="https://rajmacwan.com/industry-watch.html">
</head>
<body>

<nav class="site-nav">
    <div class="container">
        <a href="index.html" class="site-logo">Raj Macwan<span class="logo-dot">.</span></a>
        <ul>
            <li><a href="index.html">Home</a></li>
            <li><a href="about.html">About</a></li>
            <li><a href="expertise.html">Expertise</a></li>
            <li><a href="blog/index.html">Blog</a></li>
            <li><a href="research.html">Research</a></li>
            <li><a href="mit-journey.html">MIT</a></li>
            <li><a href="industry-watch.html" class="active">Industry Watch</a></li>
            <li><a href="contact.html" class="nav-cta">Connect</a></li>
        </ul>
    </div>
</nav>

<main>
    <section class="section">
        <div class="container">
            <div class="section-heading">
                <span class="eyebrow">Industry Watch</span>
                <h1>What I'm reading.</h1>
                <p class="section-lede">
                    A curated feed of recent publications from sources I trust on infrastructure,
                    cybersecurity, AI, and the practice of IT leadership. Auto-refreshed every 6 hours.
                </p>
                <p style="color: var(--text-muted); font-size: 0.9rem; margin-top: 1rem;">
                    Last refresh: <strong>{last_updated}</strong> &middot; {len(all_sorted)} articles shown &middot; {len(FEEDS)} sources
                </p>
            </div>

            <div class="section-heading" style="margin-top: 2rem;">
                <span class="eyebrow">All Categories</span>
                <h2>Latest — Mixed Feed</h2>
                <p class="section-lede">Newest first, across all tracked sources.</p>
            </div>
            {latest_html}

            {category_html}

            <div class="section-heading" style="margin-top: 4rem;">
                <span class="eyebrow">Transparency</span>
                <h2>Sources I Track</h2>
                <p class="section-lede">
                    These are the feeds I personally read. If you have a recommendation for
                    another trusted source, <a href="contact.html">let me know</a>.
                </p>
            </div>
            {sources_html}
        </div>
    </section>
</main>

<footer class="site-footer">
    <div class="container">
        <div class="footer-grid">
            <div class="footer-col brand">
                <div class="site-logo">Raj Macwan<span class="logo-dot">.</span></div>
                <p class="mt-2">IT infrastructure, cybersecurity, and emerging technology — from a practitioner's desk.</p>
            </div>
            <div class="footer-col">
                <h4>Site</h4>
                <ul>
                    <li><a href="index.html">Home</a></li>
                    <li><a href="about.html">About</a></li>
                    <li><a href="expertise.html">Expertise</a></li>
                    <li><a href="blog/index.html">Blog</a></li>
                </ul>
            </div>
            <div class="footer-col">
                <h4>Deeper</h4>
                <ul>
                    <li><a href="research.html">Research</a></li>
                    <li><a href="mit-journey.html">MIT Journey</a></li>
                    <li><a href="industry-watch.html">Industry Watch</a></li>
                    <li><a href="blog/feed.xml">RSS Feed</a></li>
                </ul>
            </div>
            <div class="footer-col">
                <h4>Connect</h4>
                <ul>
                    <li><a href="https://www.linkedin.com/in/raj-macwan" target="_blank" rel="noopener">LinkedIn ↗</a></li>
                    <li><a href="contact.html">Contact</a></li>
                </ul>
            </div>
        </div>
        <div class="footer-bottom">
            <span>© 2026 Raj Macwan. Views are my own.</span>
            <span>Last industry watch refresh: {last_updated} UTC</span>
        </div>
    </div>
</footer>

<script src="https://platform.linkedin.com/badges/js/profile.js" async defer type="text/javascript"></script>
</body>
</html>
"""
    return page


def main():
    log.info("=" * 60)
    log.info("Industry Watch aggregator starting")
    log.info("=" * 60)

    WEB_ROOT.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    all_articles = []
    for name, url, category in FEEDS:
        all_articles.extend(fetch_feed(name, url, category))

    log.info("Total articles: %d", len(all_articles))

    last_updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    page_html = render_page(all_articles, last_updated)

    (WEB_ROOT / "industry-watch.html").write_text(page_html, encoding="utf-8")
    log.info("Wrote industry-watch.html")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
