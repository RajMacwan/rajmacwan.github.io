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

def main():
    draft = find_draft()
    if not draft:
        print(f"No draft for {dt.date.today().strftime('%Y-%m')} — skipping.")
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
