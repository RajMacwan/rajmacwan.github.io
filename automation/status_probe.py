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
import xml.etree.ElementTree as ET
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


# (slug, display_name, category_id, adapter, source URL)
#  adapter ∈ {"statuspage", "azure_rss", "aws_rss", "gcp_json", "salesforce_json"}
SERVICES = [
    # ☁️ Cloud & CDN
    ("cloudflare",    "Cloudflare",    "cloud",    "statuspage", "https://www.cloudflarestatus.com/api/v2/summary.json"),
    ("fastly",        "Fastly",        "cloud",    "statuspage", "https://status.fastly.com/api/v2/summary.json"),
    ("vercel",        "Vercel",        "cloud",    "statuspage", "https://www.vercel-status.com/api/v2/summary.json"),
    ("netlify",       "Netlify",       "cloud",    "statuspage", "https://www.netlifystatus.com/api/v2/summary.json"),
    ("render",        "Render",        "cloud",    "statuspage", "https://status.render.com/api/v2/summary.json"),
    ("digitalocean",  "DigitalOcean",  "cloud",    "statuspage", "https://status.digitalocean.com/api/v2/summary.json"),
    ("heroku",        "Heroku",        "cloud",    "statuspage", "https://status.heroku.com/api/v2/summary.json"),
    ("linode",        "Akamai (Linode)","cloud",   "statuspage", "https://status.linode.com/api/v2/summary.json"),

    # 🏢 Enterprise & Data — custom adapters where Statuspage isn't used
    ("aws",           "AWS",           "enterprise", "aws_rss",         "https://status.aws.amazon.com/rss/all.rss"),
    ("azure",         "Microsoft Azure","enterprise","azure_rss",       "https://status.azure.com/en-us/status/feed/"),
    ("gcp",           "Google Cloud",  "enterprise", "gcp_json",        "https://status.cloud.google.com/incidents.json"),
    ("oci",           "Oracle Cloud (OCI)","enterprise","statuspage",   "https://ocistatus.oraclecloud.com/api/v2/summary.json"),
    ("salesforce",    "Salesforce",    "enterprise", "salesforce_json", "https://api.status.salesforce.com/v1/incidents?status=Active"),
    ("sap",           "SAP",           "enterprise", "statuspage",      "https://status.sap.com/api/v2/summary.json"),
    ("servicenow",    "ServiceNow",    "enterprise", "statuspage",      "https://status.servicenow.com/api/v2/summary.json"),
    ("snowflake",     "Snowflake",     "enterprise", "statuspage",      "https://status.snowflake.com/api/v2/summary.json"),
    ("databricks",    "Databricks",    "enterprise", "statuspage",      "https://status.databricks.com/api/v2/summary.json"),

    # 💼 Dev & Productivity
    ("github",        "GitHub",        "dev",      "statuspage", "https://www.githubstatus.com/api/v2/summary.json"),
    ("gitlab",        "GitLab",        "dev",      "statuspage", "https://status.gitlab.com/api/v2/summary.json"),
    ("atlassian",     "Atlassian",     "dev",      "statuspage", "https://status.atlassian.com/api/v2/summary.json"),
    ("figma",         "Figma",         "dev",      "statuspage", "https://www.figmastatus.com/api/v2/summary.json"),
    ("linear",        "Linear",        "dev",      "statuspage", "https://status.linear.app/api/v2/summary.json"),
    ("loom",          "Loom",          "dev",      "statuspage", "https://status.loom.com/api/v2/summary.json"),
    ("asana",         "Asana",         "dev",      "statuspage", "https://trust.asana.com/api/v2/summary.json"),
    ("notion",        "Notion",        "dev",      "statuspage", "https://status.notion.so/api/v2/summary.json"),
    ("zoom",          "Zoom",          "dev",      "statuspage", "https://status.zoom.us/api/v2/summary.json"),
    ("dropbox",       "Dropbox",       "dev",      "statuspage", "https://status.dropbox.com/api/v2/summary.json"),

    # 🤖 AI Services
    ("openai",        "OpenAI",        "ai",       "statuspage", "https://status.openai.com/api/v2/summary.json"),
    ("anthropic",     "Anthropic",     "ai",       "statuspage", "https://status.anthropic.com/api/v2/summary.json"),
    ("cursor",        "Cursor",        "ai",       "statuspage", "https://status.cursor.com/api/v2/summary.json"),
    ("replicate",     "Replicate",     "ai",       "statuspage", "https://www.replicatestatus.com/api/v2/summary.json"),
    ("huggingface",   "Hugging Face",  "ai",       "statuspage", "https://status.huggingface.co/api/v2/summary.json"),
    ("together",      "Together AI",   "ai",       "statuspage", "https://status.together.ai/api/v2/summary.json"),
    ("mistral",       "Mistral",       "ai",       "statuspage", "https://status.mistral.ai/api/v2/summary.json"),

    # 🛡️ Identity & Security
    ("okta",          "Okta",          "identity", "statuspage", "https://status.okta.com/api/v2/summary.json"),
    ("auth0",         "Auth0",         "identity", "statuspage", "https://status.auth0.com/api/v2/summary.json"),
    ("onepassword",   "1Password",     "identity", "statuspage", "https://status.1password.com/api/v2/summary.json"),
    ("bitwarden",     "Bitwarden",     "identity", "statuspage", "https://status.bitwarden.com/api/v2/summary.json"),
    ("lastpass",      "LastPass",      "identity", "statuspage", "https://status.lastpass.com/api/v2/summary.json"),
    ("duo",           "Cisco Duo",     "identity", "statuspage", "https://status.duo.com/api/v2/summary.json"),
    ("crowdstrike",   "CrowdStrike",   "identity", "statuspage", "https://status.crowdstrike.com/api/v2/summary.json"),
    ("datadog",       "Datadog",       "identity", "statuspage", "https://status.datadoghq.com/api/v2/summary.json"),

    # 💳 Payments & Money
    ("stripe",        "Stripe",        "payments", "statuspage", "https://status.stripe.com/api/v2/summary.json"),
    ("plaid",         "Plaid",         "payments", "statuspage", "https://status.plaid.com/api/v2/summary.json"),
    ("square",        "Square",        "payments", "statuspage", "https://www.issquareup.com/api/v2/summary.json"),
    ("coinbase",      "Coinbase",      "payments", "statuspage", "https://status.coinbase.com/api/v2/summary.json"),

    # 📞 Dev Comms & Email
    ("twilio",        "Twilio",        "comms",    "statuspage", "https://status.twilio.com/api/v2/summary.json"),
    ("sendgrid",      "SendGrid",      "comms",    "statuspage", "https://status.sendgrid.com/api/v2/summary.json"),
    ("postmark",      "Postmark",      "comms",    "statuspage", "https://status.postmarkapp.com/api/v2/summary.json"),
    ("mailchimp",     "Mailchimp",     "comms",    "statuspage", "https://status.mailchimp.com/api/v2/summary.json"),
    ("intercom",      "Intercom",      "comms",    "statuspage", "https://www.intercomstatus.com/api/v2/summary.json"),
    ("discord",       "Discord",       "comms",    "statuspage", "https://discordstatus.com/api/v2/summary.json"),
    ("pagerduty",     "PagerDuty",     "comms",    "statuspage", "https://status.pagerduty.com/api/v2/summary.json"),
]

CATEGORIES = [
    ("cloud",      "☁️", "Cloud & CDN"),
    ("enterprise", "🏢", "Enterprise & Data"),
    ("dev",        "💼", "Dev & Productivity"),
    ("ai",         "🤖", "AI Services"),
    ("identity",   "🛡️", "Identity & Security"),
    ("payments",   "💳", "Payments & Money"),
    ("comms",      "📞", "Dev Comms & Email"),
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


def _http_get(url, accept="application/json"):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": accept,
    })
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as r:
        return r.read()


def _ok(svc, indicator, description, incident_name="", incident_url="", landing=""):
    slug, name, cat, _adapter, url = svc
    return {
        "slug": slug, "name": name, "cat": cat,
        "indicator": indicator,
        "description": description.strip()[:160],
        "incident_name": (incident_name or "").strip()[:140],
        "incident_url":  incident_url or "",
        "statuspage_url": landing or url,
        "fetched": True,
    }


def _fail(svc, exc, landing=""):
    slug, name, cat, _adapter, url = svc
    return {
        "slug": slug, "name": name, "cat": cat,
        "indicator": "unknown",
        "description": "Status feed unreachable",
        "incident_name": "",
        "incident_url":  "",
        "statuspage_url": landing or url,
        "fetched": False,
        "error": str(exc)[:120],
    }


def fetch_statuspage(svc):
    slug, name, cat, adapter, url = svc
    try:
        data = json.loads(_http_get(url, "application/json"))
        status = data.get("status") or {}
        indicator = status.get("indicator") or "none"
        description = status.get("description") or "All Systems Operational"
        incidents = data.get("incidents") or []
        first = incidents[0] if incidents else {}
        landing = url.rsplit("/api/", 1)[0]
        return _ok(svc, indicator, description,
                   first.get("name") or "",
                   first.get("shortlink") or "",
                   landing)
    except Exception as e:
        return _fail(svc, e, url.rsplit("/api/", 1)[0])


def _parse_rss_pubdate(s):
    """RFC-2822-ish — RSS feeds vary. Try common variants."""
    for fmt in ("%a, %d %b %Y %H:%M:%S %z",
                "%a, %d %b %Y %H:%M:%S GMT",
                "%a, %d %b %Y %H:%M:%S UT",
                "%a, %d %b %Y %H:%M:%S",
                "%Y-%m-%dT%H:%M:%SZ"):
        try:
            d = dt.datetime.strptime(s, fmt)
            if d.tzinfo:
                d = d.replace(tzinfo=None)
            return d
        except ValueError:
            continue
    return None


def fetch_aws_rss(svc):
    """AWS status RSS — any item from the last 12 hours = active."""
    _slug, _n, _c, _a, url = svc
    landing = "https://health.aws.amazon.com/health/status"
    try:
        root = ET.fromstring(_http_get(url, "application/rss+xml"))
        cutoff = dt.datetime.utcnow() - dt.timedelta(hours=12)
        recent = []
        for item in root.iter("item"):
            pub = item.findtext("pubDate") or ""
            when = _parse_rss_pubdate(pub)
            if when and when >= cutoff:
                recent.append({
                    "title": (item.findtext("title") or "").strip(),
                    "link":  (item.findtext("link")  or "").strip(),
                })
        if not recent:
            return _ok(svc, "none", "All AWS services operating normally", "", "", landing)
        # heuristic: if many recent advisories, mark major
        ind = "major" if len(recent) >= 4 else "minor"
        desc = f"{len(recent)} AWS advisor{'ies' if len(recent)>1 else 'y'} in last 12h"
        return _ok(svc, ind, desc, recent[0]["title"], recent[0]["link"], landing)
    except Exception as e:
        return _fail(svc, e, landing)


def fetch_azure_rss(svc):
    """Microsoft Azure RSS — same pattern as AWS."""
    _slug, _n, _c, _a, url = svc
    landing = "https://status.azure.com/en-us/status"
    try:
        root = ET.fromstring(_http_get(url, "application/rss+xml"))
        cutoff = dt.datetime.utcnow() - dt.timedelta(hours=12)
        recent = []
        for item in root.iter("item"):
            pub = item.findtext("pubDate") or ""
            when = _parse_rss_pubdate(pub)
            if when and when >= cutoff:
                recent.append({
                    "title": (item.findtext("title") or "").strip(),
                    "link":  (item.findtext("link")  or "").strip(),
                })
        if not recent:
            return _ok(svc, "none", "All Azure services operating normally", "", "", landing)
        ind = "major" if len(recent) >= 3 else "minor"
        desc = f"{len(recent)} Azure incident{'s' if len(recent)>1 else ''} in last 12h"
        return _ok(svc, ind, desc, recent[0]["title"], recent[0]["link"], landing)
    except Exception as e:
        return _fail(svc, e, landing)


def fetch_gcp_json(svc):
    """Google Cloud incidents.json — filter to active (no 'end' field)."""
    _slug, _n, _c, _a, url = svc
    landing = "https://status.cloud.google.com/"
    try:
        data = json.loads(_http_get(url, "application/json"))
        active = [i for i in data if not i.get("end")]
        if not active:
            return _ok(svc, "none", "All Google Cloud services operating normally", "", "", landing)
        # GCP severity values: "high" | "medium" | "low"
        sevs = [(i.get("severity") or "").lower() for i in active]
        if "high" in sevs:
            ind = "major"
        else:
            ind = "minor"
        first = active[0]
        title = first.get("external_desc") or first.get("most_recent_update", {}).get("text", "") or "Active incident"
        link  = first.get("uri") or landing
        if link and not link.startswith("http"):
            link = "https://status.cloud.google.com" + link
        desc = f"{len(active)} active GCP incident{'s' if len(active)>1 else ''}"
        return _ok(svc, ind, desc, title, link, landing)
    except Exception as e:
        return _fail(svc, e, landing)


def fetch_salesforce_json(svc):
    """Salesforce active-incidents JSON endpoint."""
    _slug, _n, _c, _a, url = svc
    landing = "https://status.salesforce.com/"
    try:
        data = json.loads(_http_get(url, "application/json"))
        # Response is usually a list of incidents
        if isinstance(data, dict):
            incidents = data.get("incidents") or []
        else:
            incidents = data
        active = [i for i in incidents if (i.get("affectsAll") or i.get("instanceKeys") or i.get("affectedServices"))]
        if not active:
            return _ok(svc, "none", "All Salesforce instances operational", "", "", landing)
        first = active[0]
        title = first.get("message") or first.get("incidentImpacts", [{}])[0].get("severity", "Active incident")
        return _ok(svc, "minor",
                   f"{len(active)} active Salesforce incident{'s' if len(active)>1 else ''}",
                   str(title)[:140], landing, landing)
    except Exception as e:
        return _fail(svc, e, landing)


_ADAPTERS = {
    "statuspage":      fetch_statuspage,
    "aws_rss":         fetch_aws_rss,
    "azure_rss":       fetch_azure_rss,
    "gcp_json":        fetch_gcp_json,
    "salesforce_json": fetch_salesforce_json,
}


def fetch_one(svc):
    _slug, _name, _cat, adapter, _url = svc
    func = _ADAPTERS.get(adapter, fetch_statuspage)
    try:
        return func(svc)
    except Exception as e:
        return _fail(svc, e)


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
