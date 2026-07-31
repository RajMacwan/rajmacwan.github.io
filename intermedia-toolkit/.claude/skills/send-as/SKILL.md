---
name: send-as
description: Grant or revoke Send-As permissions on Intermedia mailboxes — who can send email as which mailbox. Use when the user asks to let someone send as/on behalf of a mailbox, or to remove that access.
---

# Send-As permission changes

You are operating the Intermedia HostPilot toolkit (see the repo root CLAUDE.md
for the session model). The change is executed by
`scripts\Set-SendAsPermission.ps1`, which runs inside the user's HostPilot
PowerShell window — not in your shell.

Terminology: **Mailbox** = the identity being sent as; **Trustee** = the person
receiving the permission. "Let the assistant send as the CEO" means
Mailbox=ceo@..., Trustee=assistant@....

## Workflow

1. **Parse the request** into (Mailbox, Trustee, Action) triples with Action =
   Grant | Revoke. Confirm direction with the user if there is any ambiguity
   about who sends as whom — this is the most common mistake.
2. **For 1–3 changes**, one-off command, dry-run first:
   ```
   .\scripts\Set-SendAsPermission.ps1 -Mailbox <mbx> -Trustee <who> -Action Grant -DryRun
   ```
3. **For more**, write a CSV into `work/` with columns `Mailbox,Trustee,Action`
   and use `-CsvPath work\<file>.csv -DryRun`.
4. **After the dry-run**, read the newest `logs/ops-*.jsonl`, verify, then have
   them re-run without `-DryRun`.
5. **After the real run**, report per-row ok/error from the log.

## Rules

- Send-As grants are security-sensitive: always restate in plain language who
  will be able to send as whom before the real run, and get an explicit yes.
- The script discovers the grant/revoke cmdlet names at runtime. If it reports
  that no revoke cmdlet exists, run the calibration procedure in the root
  CLAUDE.md before retrying.
- Permission changes can take time to propagate in Exchange (often up to an
  hour, sometimes more) — mention this when reporting success.
