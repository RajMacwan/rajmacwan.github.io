#!/usr/bin/env python3
"""
monthly_publisher.py
On the 1st of each month:
  1. Look for a draft at drafts/YYYY-MM-*.html
  2. Strip the YYYY-MM- prefix from the filename
  3. Move it to blog/<slug>.html
  4. Rebuild the blog/index.html listing, feed.xml, and sitemap.xml
  5. Rebuild the post manifest so Option B can feature it

If no draft matches the current month, the script exits cleanly — the
workflow shouldn't fail just because the pipeline is empty.
"""
import datetime as dt
import html
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUTO = Path(__file__).resolve().parent
DRAFTS = ROOT / "drafts"
BLOG = ROOT / "blog"

SITE_URL = "https://macwangrid.com"

def find_draft():
    today = dt.date.today()
    prefix = today.strftime("%Y-%m")
    matches = sorted(DRAFTS.glob(f"{prefix}-*.html"))
    return matches[0] if matches else None

def promote(draft: Path) -> Path:
    # Strip YYYY-MM- prefix from the destination filename
    dest_name = re.sub(r"^\d{4}-\d{2}-", "", draft.name)
    dest = BLOG / dest_name
    if dest.exists():
        print(f"[skip] {dest.name} already exists in blog/")
        return dest
    shutil.move(str(draft), str(dest))
    print(f"Promoted {draft.name} -> blog/{dest.name}")
    return dest

def rebuild_manifest():
    subprocess.check_call([sys.executable, str(AUTO / "build_manifest.py")])

# Grids served by the weekly rotation publisher (weekly_grid_publisher.py).
# The monthly publisher must NOT publish to these — they have their own cadence.
ROTATION_GRIDS = {"threat", "infra", "dark", "ai", "intel"}

def draft_grid(draft: Path):
    """Return the grid slug from a draft's grid-pill class, or None."""
    m = re.search(r"grid-pill grid-pill-(\w+)", draft.read_text(encoding="utf-8", errors="ignore"))
    return m.group(1) if m else None

def main():
    draft = find_draft()
    if not draft:
        print(f"No draft for {dt.date.today().strftime('%Y-%m')} — skipping.")
        return
    grid = draft_grid(draft)
    if grid in ROTATION_GRIDS:
        print(f"[skip] {draft.name} is a {grid}Grid post — those five grids are "
              f"served by the weekly rotation now (weekly_grid_publisher.py). "
              f"Monthly publisher will not publish it. Leaving the draft in place.")
        return
    promote(draft)
    # Delegate index/feed/sitemap regen to the existing shell script if present
    regen = ROOT.parent / "gen_blog_index.sh"
    if regen.exists():
        print(f"Running {regen.name}...")
        subprocess.check_call(["bash", str(regen)])
    rebuild_manifest()
    print("Monthly publish complete.")

if __name__ == "__main__":
    main()
