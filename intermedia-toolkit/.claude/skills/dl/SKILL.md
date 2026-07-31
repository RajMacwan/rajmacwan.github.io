---
name: dl
description: Manage Intermedia distribution list membership — add or remove members from a prompt, a pasted list, or a CSV. Use when the user asks to add/remove people to/from a distribution list, DL, or mailing group.
---

# Distribution list membership changes

You are operating the Intermedia HostPilot toolkit (see the repo root CLAUDE.md
for the session model). The change is executed by
`scripts\Update-DLMembership.ps1`, which runs inside the user's HostPilot
PowerShell window — not in your shell.

## Workflow

1. **Parse the request** into (DistributionList, Member, Action) triples.
   Members and DLs are email addresses on the Intermedia account. If the user
   gives display names only, ask for the email addresses or check
   `reference/dl-report.csv` if it exists.
2. **For 1–3 changes**, give the user a one-off command to paste into their
   HostPilot PowerShell window, dry-run first:
   ```
   .\scripts\Update-DLMembership.ps1 -DistributionList <dl> -Add <a>,<b> -Remove <c> -DryRun
   ```
3. **For more changes**, write a CSV into `work/` (create the folder if
   needed) with columns `DistributionList,Member,Action` (Action = Add |
   Remove), then give them:
   ```
   .\scripts\Update-DLMembership.ps1 -CsvPath work\<file>.csv -DryRun
   ```
4. **After they run the dry-run**, read the newest `logs/ops-*.jsonl`, confirm
   the planned rows match the request, then tell them to re-run without
   `-DryRun`.
5. **After the real run**, read the log again and report per-row ok/error.
   For errors, diagnose from the `detail` field. If the error is a parameter
   binding problem, follow the calibration procedure in the root CLAUDE.md.

## Rules

- Never skip the dry-run step for CSV batches.
- Removals from a DL are low-risk and reversible; additions to broad lists
  (allstaff, company-wide) deserve a double-check with the user.
- Always report results from the log file, never assume success.
