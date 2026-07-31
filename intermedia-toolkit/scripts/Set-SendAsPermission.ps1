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
  Grant side uses Grant-RecipientPermission (Intermedia KB a_id 15840). The
  revoke cmdlet name is not publicly documented, so this script discovers it
  at runtime from the likely candidates. If neither exists on your build, run
  Discover-Cmdlets.ps1, check reference\cmdlet-syntax.txt for the real name,
  and recalibrate.
#>
[CmdletBinding()]
param(
    [string]$Mailbox,
    [string]$Trustee,
    [ValidateSet('Grant', 'Revoke')]
    [string]$Action = 'Grant',
    [string]$CsvPath,
    [switch]$DryRun
)

. "$PSScriptRoot\_Common.ps1"
Assert-HostPilotSession

$grantCmd = Find-FirstCmdlet -Candidates @('Grant-RecipientPermission', 'Add-RecipientPermission')
$revokeCmd = Find-FirstCmdlet -Candidates @('Revoke-RecipientPermission', 'Remove-RecipientPermission')
if (-not $grantCmd) {
    throw 'No grant cmdlet found (tried Grant-RecipientPermission, Add-RecipientPermission). Run Discover-Cmdlets.ps1 and recalibrate.'
}

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

if (($changes | Where-Object { $_.Action -eq 'Revoke' }) -and -not $revokeCmd) {
    throw 'Revoke requested, but no revoke cmdlet was found in this session. Run Discover-Cmdlets.ps1 and recalibrate.'
}

# ---- Validate that mailboxes and trustees exist before changing anything ---
$identities = @($changes | ForEach-Object { $_.Mailbox }) + @($changes | ForEach-Object { $_.Trustee })
foreach ($id in ($identities | Sort-Object -Unique)) {
    $found = Get-User $id -ErrorAction SilentlyContinue
    if (-not $found) { throw "User/mailbox not found on this account: $id" }
}

Write-Host ("Planned changes: {0}  (dry-run: {1})  grant-cmdlet: {2}  revoke-cmdlet: {3}" -f `
    $changes.Count, [bool]$DryRun, $grantCmd, $revokeCmd)
$changes | Format-Table Mailbox, Trustee, Action -AutoSize

# ---- Apply -----------------------------------------------------------------
$results = foreach ($c in $changes) {
    $target = "$($c.Trustee) send-as $($c.Mailbox)"
    if ($DryRun) {
        Write-OpLog -Script 'Set-SendAsPermission' -Action "$($c.Action)-DryRun" -Target $target -Status 'planned'
        continue
    }
    try {
        if ($c.Action -eq 'Grant') {
            & $grantCmd $c.Mailbox -Trustee $c.Trustee
        } else {
            & $revokeCmd $c.Mailbox -Trustee $c.Trustee
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
