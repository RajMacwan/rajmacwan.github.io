# Intermedia HostPilot toolkit — Claude operating guide

This folder automates Intermedia HostPilot administration (distribution list
membership, Send-As permissions, bulk user creation) through Intermedia's
**HostPilot PowerShell** app, driven by prompts to Claude Code.

## The session model — read this first

You (Claude) do NOT talk to Intermedia directly. HostPilot PowerShell is a
custom interactive shell the user downloads from HostPilot Control Panel and
logs into with their Account Contact credentials. There is no API key or
non-interactive auth. The loop is:

1. The user keeps a **logged-in HostPilot PowerShell window** open, cd'd to
   this folder.
2. You prepare/validate inputs (CSVs in `work/`), and hand the user an exact
   one-line command to paste into that window (always `-DryRun` first).
3. The scripts write structured results to `logs/ops-YYYY-MM-DD.jsonl`.
4. You read the newest log entries and report what actually happened.

Never claim an operation succeeded without reading the log. Never run the
`.ps1` scripts in your own shell — the HostPilot cmdlets don't exist there
and `Assert-HostPilotSession` will refuse anyway.

## Layout

- `scripts/` — the executors. `_Common.ps1` (helpers/logging),
  `Update-DLMembership.ps1`, `Set-SendAsPermission.ps1`, `New-BulkUsers.ps1`,
  `Get-DLReport.ps1` (read-only audit), `Discover-Cmdlets.ps1` (calibration).
- `templates/` — example CSVs showing required columns. Don't edit; copy the
  shape into `work/`.
- `work/` — per-task CSVs you generate (gitignored).
- `logs/` — JSONL operation logs (gitignored). Your source of truth.
- `reference/` — account ground truth: `cmdlet-syntax.txt` (from
  Discover-Cmdlets), `dl-report.csv` (from Get-DLReport),
  `CALIBRATION.md` (your record of script fixes).
- `.claude/skills/` — dl, send-as, new-hires, hp-calibrate.

## Safety rules

- **Dry-run first, always.** Every script supports `-DryRun`.
- **User creation incurs charges** — never pass `-Force` to New-BulkUsers.ps1;
  the typed CREATE confirmation stays.
- **Send-As direction matters**: Mailbox = identity being sent as, Trustee =
  person gaining the right. Restate in plain language before the real run.
- Batch ≤25 when creating users with Exchange mailboxes (Intermedia guidance).
- Broad-DL additions (allstaff etc.) get a double-check with the user.

## Calibration caveat

Cmdlet names come from Intermedia's KB (which is bot-blocked to scrapers, so
signatures were not fully verifiable when this was written). If any script
throws a parameter-binding or cmdlet-not-found error, invoke the
`hp-calibrate` skill: it has the user run `Discover-Cmdlets.ps1`, then you fix
the scripts against `reference/cmdlet-syntax.txt` and record changes in
`reference/CALIBRATION.md`.

## Useful account facts

- HostPilot PowerShell endpoint: cp.intermedia.net:443. Login requires being an
  Account Contact; credential type "User" (not "Administrator").
- Execution policy on the machine must be AllSigned or Unrestricted.
- Exchange permission changes can take up to ~an hour to propagate.
- Key Intermedia KB articles: 12441 (PowerShell getting started), 12512
  (distribution groups), 15840 (Grant-RecipientPermission), 12438 (users),
  12458 (mailboxes), 10025 (mass user import UI alternative).
