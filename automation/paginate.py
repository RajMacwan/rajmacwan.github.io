#!/usr/bin/env python3
"""
paginate.py
Regenerates paginated listing pages for each grid and the master blog index.
10 posts per page. Writes blog/index.html, blog/page-2.html, blog/page-3.html, ...

Also writes per-grid paginated pages: blog/threat-page-1.html ... for each grid
(optional — only if that grid has >10 posts).

This script reads post_manifest.json (built by build_manifest.py) for metadata.
"""
import json
import math
import re
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUTO = Path(__file__).resolve().parent
BLOG = ROOT / "blog"
MANIFEST = AUTO / "post_manifest.json"

PER_PAGE = 10

HEADER = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} — MacwanGrid</title>
    <meta name="description" content="{desc}">
    <link rel="stylesheet" href="../style.css">
    <link rel="canonical" href="https://macwangrid.com/blog/{canonical}">
    <link rel="alternate" type="application/rss+xml" title="MacwanGrid RSS" href="feed.xml">
</head>
<body>
<nav class="site-nav">
    <div class="container">
        <a href="../index.html" class="site-logo">MacwanGrid<span class="logo-dot">.</span></a>
        <ul>
            <li><a href="../index.html">Home</a></li>
            <li><a href="../threat-grid.html">ThreatGrid</a></li>
            <li><a href="../infra-grid.html">InfraGrid</a></li>
            <li><a href="../dark-grid.html">DarkGrid</a></li>
            <li><a href="../ai-grid.html">AIGrid</a></li>
            <li><a href="../intel-grid.html">IntelGrid</a></li>
            <li><a href="../lab-grid.html">LabGrid</a></li>
            <li><a href="../action-grid.html">ActionGrid</a></li>
            <li><a href="../wire-grid.html">WireGrid</a></li>
            <li><a href="../patch-grid.html">PatchGrid</a></li>
            <li><a href="../off-grid.html">OffGrid</a></li>
            <li><a href="../contact.html" class="nav-cta">Connect</a></li>
        </ul>
    </div>
</nav>

<main>
    <section class="section">
        <div class="container-narrow">
            <div class="section-heading">
                <span class="eyebrow">{eyebrow}</span>
                <h1>{heading}</h1>
                <p class="section-lede">{lede}</p>
            </div>
            <div class="card-grid-2">
'''

FOOTER = '''            </div>
            {pagination}
        </div>
    </section>
</main>

<footer class="site-footer">
    <div class="container">
        <div class="footer-bottom">
            <span>© 2026 Raj Macwan.</span>
            <span>MacwanGrid — The Art of Smart Technologies.</span>
        </div>
    </div>
</footer>
</body>
</html>
'''

def card(p):
    return f'''                <a href="{p['slug']}.html" class="post-card">
                    <div class="post-meta">
                        <span class="grid-pill {p['pill_class']}">{p['grid']}</span>
                        <span>{p.get('date','')}</span>
                    </div>
                    <h3>{p['title']}</h3>
                    <p>{p.get('summary','')}</p>
                </a>
'''

def pagination(current: int, total: int, base: str):
    """
    base: filename pattern, e.g. "index" or "page-{n}" stem.
          For master index:  page 1 -> "index.html", page N>1 -> "page-{N}.html"
    """
    def href(n):
        if n == 1:
            return "index.html" if base == "index" else f"{base}-1.html"
        if base == "index":
            return f"page-{n}.html"
        return f"{base}-{n}.html"

    if total <= 1:
        return ""

    parts = ['<nav class="pagination" aria-label="Pagination">']
    if current > 1:
        parts.append(f'<a href="{href(current-1)}">← Prev</a>')
    else:
        parts.append('<span class="disabled">← Prev</span>')

    for n in range(1, total+1):
        if n == current:
            parts.append(f'<span class="current">{n}</span>')
        else:
            parts.append(f'<a href="{href(n)}">{n}</a>')

    if current < total:
        parts.append(f'<a href="{href(current+1)}">Next →</a>')
    else:
        parts.append('<span class="disabled">Next →</span>')

    parts.append('</nav>')
    return "\n            ".join(parts)

def by_date_desc(posts):
    return sorted(posts, key=lambda p: p.get("date") or "0000-00-00", reverse=True)

def paginate_master(posts):
    posts = by_date_desc(posts)
    total_pages = max(1, math.ceil(len(posts) / PER_PAGE))
    for n in range(1, total_pages+1):
        chunk = posts[(n-1)*PER_PAGE : n*PER_PAGE]
        fname = "index.html" if n == 1 else f"page-{n}.html"
        html = HEADER.format(
            title="All Posts" + (f" — Page {n}" if n > 1 else ""),
            desc=f"All MacwanGrid articles — {len(posts)} posts across 10 grids.",
            canonical=fname,
            eyebrow="All Posts",
            heading=f"From the blog.{' — page '+str(n) if n>1 else ''}",
            lede=f"{len(posts)} articles across 10 grids. Newest first. "
                 f'Filter by grid via the nav above, or <a href="feed.xml">subscribe via RSS</a>.',
        )
        html += "".join(card(p) for p in chunk)
        html += FOOTER.format(pagination=pagination(n, total_pages, "index"))
        (BLOG / fname).write_text(html, encoding="utf-8")
    print(f"Master: {total_pages} page(s), {len(posts)} posts")
    # Clean up stale page files
    for f in BLOG.glob("page-*.html"):
        try:
            n = int(f.stem.split("-")[1])
            if n > total_pages:
                f.unlink()
                print(f"Removed stale {f.name}")
        except Exception:
            pass

def main():
    if not MANIFEST.exists():
        print("[skip] No manifest. Run build_manifest.py first.")
        return
    posts = json.loads(MANIFEST.read_text(encoding="utf-8"))
    paginate_master(posts)
    print(f"Done. Wrote paginated index for {len(posts)} posts.")

if __name__ == "__main__":
    main()
