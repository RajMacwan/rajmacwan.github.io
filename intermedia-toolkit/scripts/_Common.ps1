# Shared helpers for the Intermedia HostPilot toolkit.
# Every script dot-sources this file:  . "$PSScriptRoot\_Common.ps1"
#
# These scripts run INSIDE the HostPilot PowerShell app (the custom shell
# downloaded from HostPilot Control Panel), after an interactive login.
# They will refuse to run in a plain PowerShell window.

$script:ToolkitRoot = Split-Path $PSScriptRoot -Parent
$script:LogDir      = Join-Path $script:ToolkitRoot 'logs'

function Initialize-Toolkit {
    if (-not (Test-Path $script:LogDir)) {
        New-Item -ItemType Directory -Path $script:LogDir | Out-Null
    }
}

function Assert-HostPilotSession {
    # HostPilot cmdlets only exist inside the HostPilot PowerShell host after login.
    if (-not (Get-Command 'Get-User' -ErrorAction SilentlyContinue)) {
        throw ("HostPilot cmdlets not found. Launch the HostPilot PowerShell app, " +
               "log in with your Account Contact credentials, then run this script " +
               "from that window. See README.md.")
    }
}

function Write-OpLog {
    # Appends one JSON line per operation to logs\ops-YYYY-MM-DD.jsonl and
    # returns the entry so callers can collect results for a summary table.
    param(
        [Parameter(Mandatory)][string]$Script,
        [Parameter(Mandatory)][string]$Action,
        [Parameter(Mandatory)][string]$Target,
        [Parameter(Mandatory)][string]$Status,
        [string]$Detail = ''
    )
    Initialize-Toolkit
    $entry = [pscustomobject]@{
        timestamp = (Get-Date).ToString('o')
        script    = $Script
        action    = $Action
        target    = $Target
        status    = $Status
        detail    = $Detail
    }
    $file = Join-Path $script:LogDir ("ops-{0}.jsonl" -f (Get-Date).ToString('yyyy-MM-dd'))
    $json = $entry | ConvertTo-Json -Compress
    # Retry writes: OneDrive sync intermittently locks files on synced paths
    # ("Stream was not readable"), so one attempt is not enough.
    $written = $false
    for ($i = 0; $i -lt 5 -and -not $written; $i++) {
        try {
            Add-Content -Path $file -Value $json -ErrorAction Stop
            $written = $true
        } catch {
            Start-Sleep -Milliseconds (200 * ($i + 1))
        }
    }
    if (-not $written) { Write-Warning "Could not write to log file ${file}: $json" }
    $entry
}

function Find-FirstCmdlet {
    # Returns the first cmdlet name from the candidate list that exists in this
    # session, or $null. Used because Intermedia's public docs are incomplete —
    # some cmdlet names may differ between account builds.
    param([Parameter(Mandatory)][string[]]$Candidates)
    foreach ($name in $Candidates) {
        if (Get-Command $name -ErrorAction SilentlyContinue) { return $name }
    }
    return $null
}
