<#
.SYNOPSIS
  Bulk-creates users (and optionally Exchange mailboxes) from a CSV.
  CREATING USERS INCURS CHARGES on your Intermedia account — this script
  requires explicit confirmation unless -Force is passed, and defaults to
  a dry run preview first.

.EXAMPLE
  .\New-BulkUsers.ps1 -CsvPath ..\templates\new-users.csv -DryRun

.EXAMPLE
  .\New-BulkUsers.ps1 -CsvPath ..\templates\new-users.csv -EnableExchange
  # CSV columns: DisplayName,EmailAddress   (both mandatory; extra columns ignored)

.NOTES
  Two-step model per Intermedia's KB: New-User creates the directory user,
  Enable-ExchangeMailbox turns on the mailbox. Intermedia recommends batches
  of ~25 when creating Exchange mailboxes — the script warns above that.
  Exact New-User parameters are not publicly documented (KB is bot-blocked);
  if binding errors occur, run Discover-Cmdlets.ps1 and recalibrate.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$CsvPath,
    [switch]$EnableExchange,
    [switch]$DryRun,
    [switch]$Force
)

. "$PSScriptRoot\_Common.ps1"
Assert-HostPilotSession

if (-not (Test-Path $CsvPath)) { throw "CSV not found: $CsvPath" }
$rows = @(Import-Csv $CsvPath)
if ($rows.Count -eq 0) { throw 'CSV is empty.' }

# ---- Validate every row before creating anything ---------------------------
$seen = @{}
foreach ($row in $rows) {
    if (-not $row.DisplayName -or -not $row.EmailAddress) {
        throw "Every row needs DisplayName and EmailAddress (Intermedia's two mandatory fields). Bad row: $($row | ConvertTo-Json -Compress)"
    }
    if ($row.EmailAddress -notmatch '^[^@\s]+@[^@\s]+\.[^@\s]+$') {
        throw "Invalid email address format: '$($row.EmailAddress)'"
    }
    if ($seen.ContainsKey($row.EmailAddress.ToLower())) {
        throw "Duplicate email address in CSV: $($row.EmailAddress)"
    }
    $seen[$row.EmailAddress.ToLower()] = $true
    $existing = Get-User $row.EmailAddress -ErrorAction SilentlyContinue
    if ($existing) { throw "User already exists on the account: $($row.EmailAddress)" }
}

if ($EnableExchange -and $rows.Count -gt 25) {
    Write-Warning ("{0} users with Exchange mailboxes exceeds Intermedia's recommended batch of 25. " -f $rows.Count)
    Write-Warning 'Consider splitting the CSV into smaller files.'
}

Write-Host ("Validated {0} users. Exchange mailboxes: {1}. Dry-run: {2}" -f $rows.Count, [bool]$EnableExchange, [bool]$DryRun)
$rows | Format-Table DisplayName, EmailAddress -AutoSize

if ($DryRun) {
    foreach ($row in $rows) {
        Write-OpLog -Script 'New-BulkUsers' -Action 'Create-DryRun' -Target $row.EmailAddress -Status 'planned' | Out-Null
    }
    Write-Host 'Dry run only - nothing was created.'
    return
}

# ---- Charges confirmation --------------------------------------------------
if (-not $Force) {
    Write-Host ''
    Write-Warning ("You are about to CREATE {0} user(s){1}. This INCURS CHARGES on your Intermedia account." -f `
        $rows.Count, $(if ($EnableExchange) { ' with Exchange mailboxes' } else { '' }))
    $answer = Read-Host "Type CREATE to proceed"
    if ($answer -cne 'CREATE') { Write-Host 'Aborted - nothing was created.'; return }
}

# ---- Create ----------------------------------------------------------------
$results = foreach ($row in $rows) {
    try {
        New-User -DisplayName $row.DisplayName -EmailAddress $row.EmailAddress
        Write-OpLog -Script 'New-BulkUsers' -Action 'New-User' -Target $row.EmailAddress -Status 'ok'
        if ($EnableExchange) {
            try {
                Enable-ExchangeMailbox $row.EmailAddress
                Write-OpLog -Script 'New-BulkUsers' -Action 'Enable-ExchangeMailbox' -Target $row.EmailAddress -Status 'ok'
            } catch {
                Write-OpLog -Script 'New-BulkUsers' -Action 'Enable-ExchangeMailbox' -Target $row.EmailAddress -Status 'error' -Detail $_.Exception.Message
            }
        }
    } catch {
        Write-OpLog -Script 'New-BulkUsers' -Action 'New-User' -Target $row.EmailAddress -Status 'error' -Detail $_.Exception.Message
    }
}

$results | Format-Table timestamp, action, target, status, detail -AutoSize
$errors = @($results | Where-Object { $_.status -eq 'error' })
Write-Host ("Done. {0} ok, {1} errors. Log: logs\ops-{2}.jsonl" -f `
    @($results | Where-Object { $_.status -eq 'ok' }).Count, $errors.Count, (Get-Date).ToString('yyyy-MM-dd'))
if ($errors.Count -gt 0) { exit 1 }
