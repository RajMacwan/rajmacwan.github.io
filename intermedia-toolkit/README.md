# Intermedia HostPilot automation toolkit

Prompt-driven administration of Intermedia hosted Exchange via HostPilot
PowerShell + Claude Code. Built for: distribution list membership, Send-As
permissions, and bulk user/mailbox creation from CSVs.

## One-time setup (on a Windows machine)

1. **Get this folder onto the machine** — clone the repo branch or copy the
   `intermedia-toolkit/` folder anywhere convenient.
2. **Install HostPilot PowerShell**: log in to HostPilot Control Panel, find
   the HostPilot PowerShell download (KB article a_id 12441, "Getting Started
   With HostPilot PowerShell"), download the zip and extract to
   `Documents\HostPilot.PowerShell`. You must be listed as an **Account
   Contact** on the Intermedia account.
3. **Execution policy** (admin PowerShell, once):
   `Set-ExecutionPolicy AllSigned` (or `Unrestricted`). The HostPilot app
   fails to load without this.
4. **Network**: outbound HTTPS (443) to `cp.intermedia.net` must be open.
5. **Install Claude Code** (https://claude.com/claude-code) and open this
   folder with it.

## Daily use

1. Launch the HostPilot PowerShell app and log in (credential type **User**;
   Advisor-model sub-accounts enter account type **SEH**). `cd` to this
   folder.
2. In Claude Code, just ask — e.g.:
   - "add jane and alex to the sales DL, remove bob"
   - "give the assistant send-as on the CEO mailbox"
   - "create these 12 new hires with mailboxes" (paste or attach the list)
   - "audit all DLs and show me who's in what"
3. Claude prepares validated CSVs and hands you an exact command to paste into
   the HostPilot window — always a `-DryRun` preview first. You paste, it
   prints the plan, Claude reads the log, and only then do you run it for
   real.

## First session: calibrate

Intermedia's KB is bot-blocked, so cmdlet parameter signatures in these
scripts are best-effort. In your first logged-in session run:

```
.\scripts\Discover-Cmdlets.ps1
```

then ask Claude to "calibrate the toolkit" (the hp-calibrate skill). It reads
the generated `reference\cmdlet-syntax.txt` and aligns the scripts with your
account's actual cmdlets. Also worth running once: `.\scripts\Get-DLReport.ps1`
to snapshot current DL membership into `reference\dl-report.csv`.

## Scripts

| Script | What it does |
|---|---|
| `Update-DLMembership.ps1` | Add/remove DL members (params or CSV), dry-run, per-row logging |
| `Set-SendAsPermission.ps1` | Grant/revoke Send-As (params or CSV), dry-run, runtime cmdlet discovery |
| `New-BulkUsers.ps1` | Bulk user + Exchange mailbox creation from CSV; charges-gated with typed CREATE confirmation |
| `Get-DLReport.ps1` | Read-only audit of all DLs and members to CSV |
| `Discover-Cmdlets.ps1` | Dumps real cmdlet syntax for calibration |

All operations append JSON lines to `logs\ops-YYYY-MM-DD.jsonl` — that file is
the audit trail and what Claude reports from.

## Safety design

- Nothing changes without a dry-run preview.
- All inputs validated before any change (DLs/users must exist; CSV columns
  checked; duplicate/format checks on new users).
- User creation requires typing `CREATE` interactively — charges apply.
- Every operation logged with timestamp, target, status, and error detail.
