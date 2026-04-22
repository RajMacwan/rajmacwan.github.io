#!/usr/bin/env python3
"""
weekly_breached.py
Auto-appends a placeholder "Week of YYYY-MM-DD" entry to BreachedGrid so the
accordion always shows the current week at the top. You (Raj) fill in the
actual breach content manually — the workflow just makes sure the scaffold
is there every Friday.

If a current-week entry already exists, this is a no-op.
"""
import datetime as dt
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WIRE = ROOT / "breached-grid.html"

START = "<!-- BREACHED_LOG_START -->"

def main():
    if not WIRE.exists():
        print("[skip] breached-grid.html missing.")
        return

    today = dt.date.today()
    # Snap to previous Monday (start-of-week)
    monday = today - dt.timedelta(days=today.weekday())
    key = f"Week of {monday.isoformat()}"

    html = WIRE.read_text(encoding="utf-8")
    if key in html:
        print(f"[skip] Entry for {key} already present.")
        return

    placeholder = f'''
                <details class="accordion">
                    <summary>
                        <span class="accordion-header-label">{key} · <em style="color: var(--text-muted);">pending reflection</em></span>
                        <span class="accordion-header-meta">auto-scaffold</span>
                    </summary>
                    <div class="accordion-body">
                        <p style="color: var(--text-muted); font-style: italic;">
                            Draft placeholder auto-created by the Friday scheduler. Raj will fill
                            this in with the week's most notable publicly-disclosed breach.
                        </p>
                    </div>
                </details>
'''

    idx = html.find(START)
    if idx == -1:
        print("[error] BREACHED_LOG_START marker not found.")
        return
    insert_at = idx + len(START) + 1  # after newline
    # Find indent of first existing <details> to match
    new_html = html[:insert_at] + "            " + placeholder.lstrip() + html[insert_at:]
    WIRE.write_text(new_html, encoding="utf-8")
    print(f"Added scaffold for {key}")

if __name__ == "__main__":
    main()
