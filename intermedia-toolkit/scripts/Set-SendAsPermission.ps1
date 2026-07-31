<#
.SYNOPSIS
  Grants or revokes Send-As (recipient) permissions — one-off from parameters,
  or in bulk from a CSV. Supports -DryRun and logs to logs\ops-*.jsonl.

.EXAMPLE
  .\Set-SendAsPermission.ps1 -Mailbox ceo@yourdomain.com -Trustee assistant@yourdomain.com -DryRun

.EXAMPLE
  .\Set-SendAsPermission.ps1 -Mailbox info@yourdomain.com -Trustee jdoe@yourdomain.com -Action Revoke

.EXAMPLE
  .\Set-SendAsPermission.ps1 -CsvPath ..\templates\sendas-changes.csv
  # CSV columns: Mailbox,Trustee,Action   (Action = Grant | Revoke)

.NOTES
  Calibrated 2026-07-31 against the DEX environment's actual signatures
  (see reference\CALIBRATION.md):
    Grant-RecipientPermission  -Identity <mailbox> -Recipient <trustee> -AccessRights <string>
    Revoke-RecipientPermission -Identity <mailbox> -Recipient <trustee> -AccessRights <string>
  -AccessRights defaults to 'SendAs'. If the server rejects that value, try
  'Send-As' or run Get-Help Grant-RecipientPermission in the DEX session to
  see the accepted strings, then pass -AccessRights explicitly.
#>
[CmdletBinding()]
param(
    [string]$Mailbox,
    [string]$Trustee,
    [ValidateSet('Grant', 'Revoke')]
    [string]$Action = 'Grant',
    [string]$AccessRights = 'SendAs',
    [string]$CsvPath,
    [switch]$DryRun
)

. "$PSScriptRoot\_Common.ps1"
Assert-HostPilotSession

# ---- Build the change list -------------------------------------------------
$changes = @()
if ($CsvPath) {
    if (-not (Test-Path $CsvPath)) { throw "CSV not found: $CsvPath" }
    foreach ($row in (Import-Csv $CsvPath)) {
        if (-not $row.Mailbox -or -not $row.Trustee -or -not $row.Action) {
            throw "Every CSV row needs Mailbox, Trustee and Action columns. Bad row: $($row | ConvertTo-Json -Compress)"
        }
        if ($row.Action -notin @('Grant', 'Revoke')) {
            throw "Action must be 'Grant' or 'Revoke' (got '$($row.Action)' for trustee '$($row.Trustee)')"
        }
        $changes += [pscustomobject]@{
            Mailbox = $row.Mailbox.Trim()
            Trustee = $row.Trustee.Trim()
            Action  = $row.Action.Trim()
        }
    }
} else {
    if (-not $Mailbox -or -not $Trustee) { throw 'Provide -CsvPath, or both -Mailbox and -Trustee.' }
    $changes += [pscustomobject]@{ Mailbox = $Mailbox; Trustee = $Trustee; Action = $Action }
}

# ---- Validate and resolve mailboxes/trustees before changing anything ------
# Identity params accept only GUID/DistinguishedName (KB 12330), so emails
# are resolved to identity strings up front; failure aborts everything.
$idMap = @{}
$identities = @($changes | ForEach-Object { $_.Mailbox }) + @($changes | ForEach-Object { $_.Trustee })
foreach ($id in ($identities | Sort-Object -Unique)) {
    $idMap[$id] = Get-HPIdentityString (Resolve-HPRecipient -Email $id)
}

Write-Host ("Planned changes: {0}  (dry-run: {1})  access-rights: {2}" -f $changes.Count, [bool]$DryRun, $AccessRights)
$changes | Format-Table Mailbox, Trustee, Action -AutoSize

# ---- Apply -----------------------------------------------------------------
$results = foreach ($c in $changes) {
    $target = "$($c.Trustee) $AccessRights $($c.Mailbox)"
    if ($DryRun) {
        Write-OpLog -Script 'Set-SendAsPermission' -Action "$($c.Action)-DryRun" -Target $target -Status 'planned'
        continue
    }
    try {
        if ($c.Action -eq 'Grant') {
            Grant-RecipientPermission -Identity $idMap[$c.Mailbox] -Recipient $idMap[$c.Trustee] -AccessRights $AccessRights
        } else {
            Revoke-RecipientPermission -Identity $idMap[$c.Mailbox] -Recipient $idMap[$c.Trustee] -AccessRights $AccessRights
        }
        Write-OpLog -Script 'Set-SendAsPermission' -Action $c.Action -Target $target -Status 'ok'
    } catch {
        Write-OpLog -Script 'Set-SendAsPermission' -Action $c.Action -Target $target -Status 'error' -Detail $_.Exception.Message
    }
}

$results | Format-Table timestamp, action, target, status, detail -AutoSize
$errors = @($results | Where-Object { $_.status -eq 'error' })
Write-Host ("Done. {0} ok, {1} errors. Log: logs\ops-{2}.jsonl" -f `
    @($results | Where-Object { $_.status -eq 'ok' }).Count, $errors.Count, (Get-Date).ToString('yyyy-MM-dd'))
if ($errors.Count -gt 0) { exit 1 }
