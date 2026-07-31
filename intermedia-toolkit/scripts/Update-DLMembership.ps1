<#
.SYNOPSIS
  Adds/removes distribution list members — one-off from parameters, or in bulk
  from a CSV. Validates everything before changing anything, supports -DryRun,
  and logs every operation to logs\ops-*.jsonl.

.EXAMPLE
  .\Update-DLMembership.ps1 -DistributionList sales@yourdomain.com -Add jdoe@yourdomain.com -DryRun

.EXAMPLE
  .\Update-DLMembership.ps1 -DistributionList sales@yourdomain.com -Add jdoe@yourdomain.com,asmith@yourdomain.com -Remove old@yourdomain.com

.EXAMPLE
  .\Update-DLMembership.ps1 -CsvPath ..\templates\dl-changes.csv
  # CSV columns: DistributionList,Member,Action   (Action = Add | Remove)

.NOTES
  Calibrated 2026-07-31 against the DEX environment's actual signatures
  (see reference\CALIBRATION.md): -Identity <dl> -Members <array>.
#>
[CmdletBinding()]
param(
    [string]$DistributionList,
    [string[]]$Add = @(),
    [string[]]$Remove = @(),
    [string]$CsvPath,
    [switch]$DryRun
)

. "$PSScriptRoot\_Common.ps1"
Assert-HostPilotSession

# ---- Build a flat change list from either input style ----------------------
$changes = @()
if ($CsvPath) {
    if (-not (Test-Path $CsvPath)) { throw "CSV not found: $CsvPath" }
    foreach ($row in (Import-Csv $CsvPath)) {
        if (-not $row.DistributionList -or -not $row.Member -or -not $row.Action) {
            throw "Every CSV row needs DistributionList, Member and Action columns. Bad row: $($row | ConvertTo-Json -Compress)"
        }
        if ($row.Action -notin @('Add', 'Remove')) {
            throw "Action must be 'Add' or 'Remove' (got '$($row.Action)' for member '$($row.Member)')"
        }
        $changes += [pscustomobject]@{
            DL     = $row.DistributionList.Trim()
            Member = $row.Member.Trim()
            Action = $row.Action.Trim()
        }
    }
} else {
    if (-not $DistributionList) { throw 'Provide -CsvPath, or -DistributionList with -Add and/or -Remove.' }
    if (-not $Add -and -not $Remove) { throw 'Nothing to do: pass -Add and/or -Remove members.' }
    foreach ($m in $Add)    { $changes += [pscustomobject]@{ DL = $DistributionList; Member = $m; Action = 'Add' } }
    foreach ($m in $Remove) { $changes += [pscustomobject]@{ DL = $DistributionList; Member = $m; Action = 'Remove' } }
}

# ---- Validate and resolve all targets BEFORE touching anything -------------
# Identity params accept only GUID/DistinguishedName (KB 12330), so emails
# are resolved to DN strings up front; resolution failure aborts everything.
$dlMap = @{}
foreach ($dl in ($changes | ForEach-Object { $_.DL } | Sort-Object -Unique)) {
    $dlMap[$dl] = Get-HPIdentityString (Resolve-HPDistributionGroup -Email $dl)
}
$memberMap = @{}
foreach ($m in ($changes | ForEach-Object { $_.Member } | Sort-Object -Unique)) {
    $memberMap[$m] = Get-HPIdentityString (Resolve-HPRecipient -Email $m)
}

Write-Host ("Planned changes: {0}  (dry-run: {1})" -f $changes.Count, [bool]$DryRun)
$changes | Format-Table DL, Member, Action -AutoSize

# ---- Apply -----------------------------------------------------------------
$results = foreach ($c in $changes) {
    $target = "$($c.Member) -> $($c.DL)"
    if ($DryRun) {
        Write-OpLog -Script 'Update-DLMembership' -Action "$($c.Action)-DryRun" -Target $target -Status 'planned'
        continue
    }
    try {
        if ($c.Action -eq 'Add') {
            Add-DistributionGroupMember -Identity $dlMap[$c.DL] -Members $memberMap[$c.Member]
        } else {
            Remove-DistributionGroupMember -Identity $dlMap[$c.DL] -Members $memberMap[$c.Member] -Confirm:$false
        }
        Write-OpLog -Script 'Update-DLMembership' -Action $c.Action -Target $target -Status 'ok'
    } catch {
        Write-OpLog -Script 'Update-DLMembership' -Action $c.Action -Target $target -Status 'error' -Detail $_.Exception.Message
    }
}

$results | Format-Table timestamp, action, target, status, detail -AutoSize
$errors = @($results | Where-Object { $_.status -eq 'error' })
Write-Host ("Done. {0} ok, {1} errors. Log: logs\ops-{2}.jsonl" -f `
    @($results | Where-Object { $_.status -eq 'ok' }).Count, $errors.Count, (Get-Date).ToString('yyyy-MM-dd'))
if ($errors.Count -gt 0) { exit 1 }
