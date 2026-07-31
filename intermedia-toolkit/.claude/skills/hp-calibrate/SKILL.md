---
name: hp-calibrate
description: Calibrate the Intermedia toolkit scripts against the account's actual HostPilot PowerShell cmdlets. Use on first setup, or whenever a toolkit script fails with a parameter binding or cmdlet-not-found error.
---

# Calibrating against the real cmdlet surface

Intermedia's public KB is bot-blocked, so this toolkit was written from
search-indexed documentation. Cmdlet names are believed correct
(`New-User`, `Enable-ExchangeMailbox`, `Add-DistributionGroupMember`,
`Remove-DistributionGroupMember`, `Get-DistributionGroup`,
`Grant-RecipientPermission`, `Add-EmailAddress`, `Set-PrimaryEmailAddress`)
but exact parameter signatures were not verifiable. This skill fixes that
once, against ground truth.

## Procedure

1. Ask the user to run, inside their logged-in HostPilot PowerShell window:
   ```
   .\scripts\Discover-Cmdlets.ps1
   ```
   This writes every relevant cmdlet's real syntax to
   `reference/cmdlet-syntax.txt`.
2. Read `reference/cmdlet-syntax.txt`. For each toolkit script
   (`Update-DLMembership.ps1`, `Set-SendAsPermission.ps1`,
   `New-BulkUsers.ps1`, `Get-DLReport.ps1`), compare the cmdlet calls against
   the real signatures: cmdlet names, parameter names, mandatory parameters,
   identity-vs-named-parameter conventions.
3. Edit the scripts to match reality. Keep the dry-run, validation, logging,
   and confirmation structure intact — only adjust the cmdlet invocation
   lines.
4. Record what you changed in `reference/CALIBRATION.md` (create it): date,
   cmdlet, before → after. Future sessions read this instead of re-deriving.
5. Have the user re-run the failed operation with `-DryRun` to confirm the
   fix, then proceed normally.
