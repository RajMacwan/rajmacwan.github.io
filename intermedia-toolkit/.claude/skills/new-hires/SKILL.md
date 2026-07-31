---
name: new-hires
description: Bulk-create Intermedia users and Exchange mailboxes from a list or CSV of new hires. Use when the user asks to create users, mailboxes, or email addresses — INCURS CHARGES, so this flow is confirmation-heavy by design.
---

# Bulk user / mailbox creation

You are operating the Intermedia HostPilot toolkit (see the repo root CLAUDE.md
for the session model). Execution is via `scripts\New-BulkUsers.ps1` inside the
user's HostPilot PowerShell window.

**Creating users incurs charges on the Intermedia account.** Never present the
non-dry-run command until the user has confirmed the exact list.

## Workflow

1. **Collect the user list** (pasted, from a file, wherever). Normalize into a
   CSV in `work/` with columns `DisplayName,EmailAddress` — Intermedia's two
   mandatory fields. Validate: email format, no duplicates, domain is one the
   user says is registered on the account (Services > Domains).
2. **Batch**: if creating Exchange mailboxes and the list exceeds 25, split
   into multiple CSVs of ≤25 (Intermedia's recommended batch size).
3. **Dry-run**:
   ```
   .\scripts\New-BulkUsers.ps1 -CsvPath work\<file>.csv -EnableExchange -DryRun
   ```
4. **Read the log**, show the user exactly what will be created, restate that
   charges apply, and get an explicit yes.
5. **Real run**: same command without `-DryRun`. The script itself asks them to
   type CREATE as a final gate.
6. **Report** per-row results from `logs/ops-*.jsonl`. Common follow-ups:
   passwords (auto-generated and emailed by Intermedia), DL membership for the
   new users (use the dl skill), Send-As (use the send-as skill).

## Rules

- Never pass `-Force`. The interactive CREATE confirmation stays.
- If `New-User` fails with a parameter binding error, its exact parameters may
  differ on this account's build — run the calibration procedure in the root
  CLAUDE.md.
