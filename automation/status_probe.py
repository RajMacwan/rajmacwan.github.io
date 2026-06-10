#!/usr/bin/env python3
"""
status_probe.py
Polls Statuspage v2 summary APIs for ~30 major services, categorizes the
results, and injects a status board into status.html between
<!-- STATUS_BOARD_START --> and <!-- STATUS_BOARD_END -->.

stdlib-only. Parallel fetch via ThreadPoolExecutor. Fails soft per-service —
unreachable feeds render as 'unknown' rather than removing the row.

Only writes to status.html when something materially changed (any service
indicator or description differs from the cached state, OR more than an
hour has passed since the last write). Keeps the bot-commit history quiet.
"""
import concurrent.futures as cf
import datetime as dt
import json
import re
import urllib.request
from pathlib import Path

ROOT  = Path(__file__).resolve().parent.parent
AUTO  = Path(__file__).resolve().parent
PAGE  = ROOT / "status.html"
STATE = AUTO / "status_state.json"

UA = "macwangrid-status/1.0 (+https://macwangrid.com/status.html)"

START_MARKER = "<!-- STATUS_BOARD_START -->"
END_MARKER   = "<!-- STATUS_BOARD_END -->"
BANNER_START = "<!-- STATUS_BANNER_START -->"
BANNER_END   = "<!-- STATUS_BANNER_END -->"

MIN_REWRITE_MINUTES = 60   # force-refresh HTML at least hourly even with no diffs
FETCH_TIMEOUT       = 12
PARALLELISM         = 16


# (slug, display_name, category_id, statuspage summary URL)
SERVICES = [
    # ☁️ Cloud & CDN
    ("cloudflare",    "Cloudflare",    "cloud",    "https://www.cloudflarestatus.com/api/v2/summary.json"),
    ("fastly",        "Fastly",        "cloud",    "https://status.fastly.com/api/v2/summary.json"),
    ("vercel",        "Vercel",        "cloud",    "https://www.vercel-status.com/api/v2/summary.json"),
    ("netlify",       "Netlify",       "cloud",    "https://www.netlifystatus.com/api/v2/summary.json"),
    ("render",        "Render",        "cloud",    "https://status.render.com/api/v2/summary.json"),
    ("digitalocean",  "DigitalOcean",  "cloud",    "https://status.digitalocean.com/api/v2/summary.json"),
    ("heroku",        "Heroku",        "cloud",    "https://status.heroku.com/api/v2/summary.json"),
    ("linode",        "Akamai (Linode)","cloud",   "https://status.linode.com/api/v2/summary.json"),

    # 💼 Dev & Productivity
    ("github",        "GitHub",        "dev",      "https://www.githubstatus.com/api/v2/summary.json"),
    ("gitlab",        "GitLab",        "dev",      "https://status.gitlab.com/api/v2/summary.json"),
    ("atlassian",     "Atlassian",     "dev",      "https://status.atlassian.com/api/v2/summary.json"),
    ("figma",         "Figma",         "dev",      "https://www.figmastatus.com/api/v2/summary.json"),
    ("linear",        "Linear",        "dev",      "https://status.linear.app/api/v2/summary.json"),
    ("loom",          "Loom",          "dev",      "https://status.loom.com/api/v2/summary.json"),
    ("asana",         "Asana",         "dev",      "https://trust.asana.com/api/v2/summary.json"),
    ("notion",        "Notion",        "dev",      "https://status.notion.so/api/v2/summary.json"),
    ("zoom",          "Zoom",          "dev",      "https://status.zoom.us/api/v2/summary.json"),
    ("dropbox",       "Dropbox",       "dev",      "https://status.dropbox.com/api/v2/summary.json"),

    # 🤖 AI Services
    ("openai",        "OpenAI",        "ai",       "https://status.openai.com/api/v2/summary.json"),
    ("anthropic",     "Anthropic",     "ai",       "https://status.anthropic.com/api/v2/summary.json"),
    ("cursor",        "Cursor",        "ai",       "https://status.cursor.com/api/v2/summary.json"),
    ("replicate",     "Replicate",     "ai",       "https://www.replicatestatus.com/api/v2/summary.json"),
    ("huggingface",   "Hugging Face",  "ai",       "https://status.huggingface.co/api/v2/summary.json"),
    ("together",      "Together AI",   "ai",       "https://status.together.ai/api/v2/summary.json"),
    ("mistral",       "Mistral",       "ai",       "https://status.mistral.ai/api/v2/summary.json"),

    # 🛡️ Identity & Security
    ("okta",          "Okta",          "identity", "https://status.okta.com/api/v2/summary.json"),
    ("auth0",         "Auth0",         "identity", "https://status.auth0.com/api/v2/summary.json"),
    ("onepassword",   "1Password",     "identity", "https://status.1password.com/api/v2/summary.json"),
    ("bitwarden",     "Bitwarden",     "identity", "https://status.bitwarden.com/api/v2/summary.json"),
    ("lastpass",      "LastPass",      "identity", "https://status.lastpass.com/api/v2/summary.json"),
    ("duo",           "Cisco Duo",     "identity", "https://status.duo.com/api/v2/summary.json"),
    ("crowdstrike",   "CrowdStrike",   "identity", "https://status.crowdstrike.com/api/v2/summary.json"),
    ("datadog",       "Datadog",       "identity", "https://status.datadoghq.com/api/v2/summary.json"),

    # 💳 Payments & Money
    ("stripe",        "Stripe",        "payments", "https://status.stripe.com/api/v2/summary.json"),
    ("plaid",         "Plaid",         "payments", "https://status.plaid.com/api/v2/summary.json"),
    ("square",        "Square",        "payments", "https://www.issquareup.com/api/v2/summary.json"),
    ("coinbase",      "Coinbase",      "payments", "https://status.coinbase.com/api/v2/summary.json"),

    # 📞 Dev Comms & Email
    ("twilio",        "Twilio",        "comms",    "https://status.twilio.com/api/v2/summary.json"),
    ("sendgrid",      "SendGrid",      "comms",    "https://status.sendgrid.com/api/v2/summary.json"),
    ("postmark",      "Postmark",      "comms",    "https://status.postmarkapp.com/api/v2/summary.json"),
    ("mailchimp",     "Mailchimp",     "comms",    "https://status.mailchimp.com/api/v2/summary.json"),
    ("intercom",      "Intercom",      "comms",    "https://www.intercomstatus.com/api/v2/summary.json"),
    ("discord",       "Discord",       "comms",    "https://discordstatus.com/api/v2/summary.json"),
    ("pagerduty",     "PagerDuty",     "comms",    "https://status.pagerduty.com/api/v2/summary.json"),
]

CATEGORIES = [
    ("cloud",    "☁️", "Cloud & CDN"),
    ("dev",      "💼", "Dev & Productivity"),
    ("ai",       "🤖", "AI Services"),
    ("identity", "🛡️", "Identity & Security"),
    ("payments", "💳", "Payments & Money"),
    ("comms",    "📞", "Dev Comms & Email"),
]

# Statuspage indicator → (css class suffix, label)
INDICATOR_MAP = {
    "none":        ("op",     "Operational"),
    "minor":       ("min",    "Degraded"),
    "major":       ("maj",    "Major outage"),
    "critical":    ("crit",   "Down"),
    "maintenance": ("maint",  "Maintenance"),
    "unknown":     ("unknown","Status unknown"),
}

# Priority order for choosing overall site-wide banner level
SEVERITY = ["critical", "major", "minor", "maintenance", "unknown", "none"]


def fetch_one(svc):
    slug, name, cat, url = svc
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as r:
            data = json.loads(r.read())
        status = data.get("status") or {}
        indicator = status.get("indicator") or "none"
        description = status.get("description") or "All Systems Operational"
        incidents = data.get("incidents") or []
        first_incident = incidents[0] if incidents else {}
        statuspage_url = url.rsplit("/api/", 1)[0]
        return {
            "slug": slug,
            "name": name,
            "cat": cat,
            "indicator": indicator,
            "description": description.strip(),
            "incident_name": (first_incident.get("name") or "").strip(),
            "incident_url":  first_incident.get("shortlink") or "",
            "statuspage_url": statuspage_url,
            "fetched": True,
        }
    except Exception as e:
        return {
            "slug": slug,
            "name": name,
            "cat": cat,
            "indicator": "unknown",
            "description": "Status feed unreachable",
            "incident_name": "",
            "incident_url":  "",
            "statuspage_url": url.rsplit("/api/", 1)[0],
            "fetched": False,
            "error": str(e)[:120],
        }


def fetch_all():
    with cf.ThreadPoolExecutor(max_workers=PARALLELISM) as ex:
        return list(ex.map(fetch_one, SERVICES))


def worst_indicator(results):
    """Returns the most severe indicator across all services."""
    levels_present = {r["indicator"] for r in results}
    for lvl in SEVERITY:
        if lvl in levels_present:
            return lvl
    return "none"


def overall_banner(results):
    """Returns (slug, label, headline) for the top-of-page banner."""
    worst = worst_indicator(results)
    counts = {}
    for r in results:
        counts[r["indicator"]] = counts.get(r["indicator"], 0) + 1
    if worst in ("none",):
        return ("op",
                "All quiet across the wire.",
                f"All {len(results)} tracked services reporting operational.")
    if worst == "unknown" and counts.get("unknown", 0) >= len(results) - 2:
        return ("unknown",
                "Status feeds unavailable.",
                "Most upstream Statuspage APIs are unreachable from our prober. "
                "Try again in a few minutes.")
    label_map = {
        "critical":    ("crit", "Major outage in progress."),
        "major":       ("maj",  "Outages reported."),
        "minor":       ("min",  "Some services degraded."),
        "maintenance": ("maint","Scheduled maintenance in progress."),
        "unknown":     ("unknown","Mixed signal — some feeds offline."),
    }
    css, headline = label_map.get(worst, ("min", "Some services degraded."))
    # build a one-line summary of what's not green
    not_ok = [r for r in results if r["indicator"] not in ("none",)]
    names = ", ".join(r["name"] for r in not_ok[:5])
    extra = f" and {len(not_ok)-5} more" if len(not_ok) > 5 else ""
    detail = f"{len(not_ok)} of {len(results)} services not fully operational ({names}{extra})."
    return (css, headline, detail)


def render_service_row(r):
    css, label = INDICATOR_MAP.get(r["indicator"], INDICATOR_MAP["unknown"])
    name = r["name"]
    desc = r["description"]
    inc  = r["incident_name"]
    sp   = r["statuspage_url"]
    inc_html = ""
    if inc:
        inc_html = (f'<span class="svc-incident">'
                    f'<span class="svc-dot-min"></span>{inc}'
                    f'</span>')
    return (
        f'<a href="{sp}" target="_blank" rel="noopener" '
        f'class="svc-row svc-row-{css}">'
        f'<span class="svc-dot svc-dot-{css}" aria-hidden="true"></span>'
        f'<span class="svc-name">{name}</span>'
        f'<span class="svc-label svc-label-{css}">{label}</span>'
        f'{inc_html}'
        f'<span class="svc-arrow">↗</span>'
        f'</a>'
    )


def cat_severity(cat_id, results):
    """How bad is this category? Returns severity rank for ordering."""
    rows = [r for r in results if r["cat"] == cat_id]
    worst = "none"
    for r in rows:
        if SEVERITY.index(r["indicator"]) < SEVERITY.index(worst):
            worst = r["indicator"]
    not_green = sum(1 for r in rows if r["indicator"] not in ("none",))
    return (SEVERITY.index(worst), -not_green)


def pick_default_open(results):
    """Of all categories, pick the one with the worst severity to auto-open.
    Returns the cat_id, or None if everything is green."""
    candidates = []
    for cat_id, _, _ in CATEGORIES:
        rows = [r for r in results if r["cat"] == cat_id]
        worst = "none"
        for r in rows:
            if SEVERITY.index(r["indicator"]) < SEVERITY.index(worst):
                worst = r["indicator"]
        if worst != "none":
            candidates.append((SEVERITY.index(worst), cat_id))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][1]


def render_category_block(cat_id, emoji, title, results, default_open_cat):
    rows = [r for r in results if r["cat"] == cat_id]
    not_green = sum(1 for r in rows if r["indicator"] not in ("none",))
    is_open = (cat_id == default_open_cat)
    open_attr = " open" if is_open else ""
    badge = ""
    badge_class = ""
    if not_green > 0:
        # determine worst class for the badge accent
        worst = "min"
        for r in rows:
            ind = r["indicator"]
            if ind == "critical": worst = "crit"; break
            if ind == "major":    worst = "maj"
            if ind == "minor" and worst not in ("crit","maj"): worst = "min"
            if ind == "maintenance" and worst not in ("crit","maj","min"): worst = "maint"
        badge_class = f" cat-badge-{worst}"
        badge = f'<span class="cat-badge{badge_class}">● {not_green} of {len(rows)}</span>'
    row_html = "\n        ".join(render_service_row(r) for r in rows)
    return f'''<details class="status-cat" name="status-cats"{open_attr}>
    <summary class="cat-summary">
        <span class="cat-emoji">{emoji}</span>
        <div class="cat-title-block">
            <span class="cat-title">{title}</span>
            <span class="cat-count">{len(rows)} services</span>
        </div>
        {badge}
        <span class="cat-chevron" aria-hidden="true"></span>
    </summary>
    <div class="cat-rows">
        {row_html}
    </div>
</details>'''


def render_banner(results):
    css, headline, detail = overall_banner(results)
    return f'''<div class="status-banner status-banner-{css}">
    <div class="banner-pulse"><span class="banner-dot banner-dot-{css}"></span></div>
    <div class="banner-text">
        <strong>{headline}</strong>
        <small>{detail}</small>
    </div>
</div>'''


def render_board(results):
    default_open = pick_default_open(results)
    blocks = []
    for cat_id, emoji, title in CATEGORIES:
        blocks.append(render_category_block(cat_id, emoji, title, results, default_open))
    return "\n\n".join(blocks)


def inject(file_path: Path, start: str, end: str, replacement: str):
    html = file_path.read_text(encoding="utf-8")
    pat = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    if not pat.search(html):
        print(f"[error] markers {start}/{end} not found in {file_path.name}")
        return False
    new = pat.sub(f"{start}\n{replacement}\n{end}", html)
    file_path.write_text(new, encoding="utf-8")
    return True


def material_change(new_results, old_state):
    """Returns True if any service's indicator OR description differs from cache."""
    if not old_state:
        return True
    old_services = old_state.get("services", {})
    for r in new_results:
        prev = old_services.get(r["slug"])
        if not prev:
            return True
        if prev.get("indicator") != r["indicator"]:
            return True
        if prev.get("description") != r["description"]:
            return True
        if prev.get("incident_name") != r["incident_name"]:
            return True
    return False


def time_for_periodic_refresh(old_state):
    """Force a re-render at least every MIN_REWRITE_MINUTES even if no diff."""
    if not old_state or not old_state.get("html_written"):
        return True
    try:
        last = dt.datetime.fromisoformat(old_state["html_written"].rstrip("Z"))
    except Exception:
        return True
    age = dt.datetime.utcnow() - last
    return age >= dt.timedelta(minutes=MIN_REWRITE_MINUTES)


def load_state():
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state(results, html_written):
    state = {
        "polled":   dt.datetime.utcnow().isoformat() + "Z",
        "services": {r["slug"]: {
            "indicator":     r["indicator"],
            "description":   r["description"],
            "incident_name": r["incident_name"],
            "fetched":       r.get("fetched", False),
        } for r in results},
    }
    if html_written:
        state["html_written"] = dt.datetime.utcnow().isoformat() + "Z"
    elif STATE.exists():
        # preserve previous html_written timestamp on a no-write tick
        prev = load_state()
        if prev.get("html_written"):
            state["html_written"] = prev["html_written"]
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def main():
    results = fetch_all()
    old_state = load_state()

    should_write = material_change(results, old_state) or time_for_periodic_refresh(old_state)

    print(f"Probed {len(results)} services. "
          f"Fetched OK: {sum(1 for r in results if r.get('fetched'))}. "
          f"Worst indicator: {worst_indicator(results)}. "
          f"HTML rewrite needed: {should_write}")

    if should_write and PAGE.exists():
        board = render_board(results)
        banner = render_banner(results)
        inject(PAGE, START_MARKER, END_MARKER, board)
        inject(PAGE, BANNER_START, BANNER_END, banner)
        # Update the visible 'last refreshed' timestamp once per write
        ts = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        html = PAGE.read_text(encoding="utf-8")
        html = re.sub(r'<span class="status-updated">[^<]*</span>',
                      f'<span class="status-updated">last refresh: {ts}</span>',
                      html)
        PAGE.write_text(html, encoding="utf-8")

    save_state(results, should_write)


if __name__ == "__main__":
    main()
