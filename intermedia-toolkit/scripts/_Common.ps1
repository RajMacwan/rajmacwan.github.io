# Shared helpers for the Intermedia HostPilot toolkit.
# Every script dot-sources this file:  . "$PSScriptRoot\_Common.ps1"
#
# These scripts run INSIDE the HostPilot PowerShell session (created by
# dot-sourcing Intermedia's Hosting.Powershell.ps1 and logging in). They will
# refuse to run in a plain PowerShell window.
#
# DEX session facts this file encodes (see reference\CALIBRATION.md):
# - Cmdlets are implicit-remoting proxy FUNCTIONS; the remote module even
#   clobbers Get-Command, so capability checks must be local:
#   Test-Path function:\<name>, or the module-qualified real Get-Command.
# - Connection auth lives in the REMOTE session via Set-ConnectionSettings.
#   If the remote session drops and implicit remoting rebuilds it, those
#   settings are gone and every cmdlet starts prompting for CredentialType.
#   Ensure-HPConnection re-registers them using Intermedia's own helpers
#   (GetHPCred + Set-ConnectionSettings) and the globals their hosting script
#   sets at login ($global:desc = platform, $global:CredentialType).

$script:ToolkitRoot = Split-Path $PSScriptRoot -Parent
$script:LogDir      = Join-Path $script:ToolkitRoot 'logs'

function Initialize-Toolkit {
    if (-not (Test-Path $script:LogDir)) {
        New-Item -ItemType Directory -Path $script:LogDir | Out-Null
    }
}

function Test-HPCmdlet {
    # Local-only capability check. Never use bare Get-Command here - the
    # remote module proxies it and each call may spawn a remote session.
    param([Parameter(Mandatory)][string]$Name)
    if (Test-Path "function:\$Name") { return $true }
    return [bool](Microsoft.PowerShell.Core\Get-Command $Name -ErrorAction SilentlyContinue)
}

function Get-ToolkitAccountId {
    # The Intermedia AccountID is required by every data cmdlet when logged
    # in with the Administrator credential type. It is asked for ONCE and
    # then cached in reference\connection.local.json (gitignored - never
    # commit account identifiers to the public repo).
    if ($global:ToolkitAccountID) { return $global:ToolkitAccountID }
    $refDir  = Join-Path $script:ToolkitRoot 'reference'
    $cfgFile = Join-Path $refDir 'connection.local.json'
    if (Test-Path $cfgFile) {
        try {
            $cfg = Get-Content $cfgFile -Raw | ConvertFrom-Json
            if ($cfg.accountId) {
                $global:ToolkitAccountID = [int]$cfg.accountId
                return $global:ToolkitAccountID
            }
        } catch { }
    }
    $id = Read-Host 'Enter your Intermedia AccountID (saved locally after first entry)'
    $global:ToolkitAccountID = [int]$id
    if (-not (Test-Path $refDir)) { New-Item -ItemType Directory -Path $refDir | Out-Null }
    @{ accountId = $global:ToolkitAccountID } | ConvertTo-Json | Set-Content $cfgFile -Encoding UTF8
    return $global:ToolkitAccountID
}

function Ensure-HPConnection {
    # Make sure no HostPilot cmdlet ever prompts mid-call. A prompt in the
    # middle of a remote call stalls WinRM long enough to kill the session
    # (HTTP 12152), so ALL auth parameters are seeded up front:
    # 1. $PSDefaultParameterValues supplies CredentialType/Credential/AccountID
    #    to every toolkit-used cmdlet on every call - survives remote-session
    #    rebuilds automatically.
    # 2. Set-ConnectionSettings is also re-registered (Intermedia's own
    #    mechanism), mirroring the login logic in Hosting.Powershell.ps1.
    $plat     = $global:desc
    $credType = $global:CredentialType
    if (-not $plat -or -not $credType) {
        Write-Warning 'HostPilot login globals not found ($desc/$CredentialType); skipping connection seeding.'
        return
    }
    if (-not (Test-Path function:\GetHPCred)) {
        Write-Warning 'GetHPCred not available; skipping connection seeding.'
        return
    }
    try {
        $creds = GetHPCred -plat $plat -credentialType $credType -IgnoreExisting $false
        if ($creds -is [object[]]) { $creds = $creds[-1] }
        $accountId = Get-ToolkitAccountId

        $hpCmdlets = @(
            'Get-User', 'Set-User', 'New-User', 'Remove-User', 'Enable-User', 'Disable-User',
            'Get-UserMemberOf', 'Reset-UserPassword',
            'Get-DistributionGroup', 'Get-DistributionGroupMember',
            'Add-DistributionGroupMember', 'Remove-DistributionGroupMember',
            'New-DistributionGroup', 'Set-DistributionGroup', 'Remove-DistributionGroup',
            'Grant-RecipientPermission', 'Revoke-RecipientPermission',
            'Grant-ExchangeMailboxPermission', 'Revoke-ExchangeMailboxPermission',
            'Get-ExchangeMailbox', 'Set-ExchangeMailbox', 'Enable-ExchangeMailbox', 'Disable-ExchangeMailbox',
            'Add-EmailAddress', 'Remove-EmailAddress', 'Set-PrimaryEmailAddress',
            'Get-Domain', 'Get-OrganizationalUnit'
        )
        if ($null -eq $global:PSDefaultParameterValues) {
            $global:PSDefaultParameterValues = @{}
        }
        foreach ($n in $hpCmdlets) {
            $global:PSDefaultParameterValues["${n}:CredentialType"] = $credType
            $global:PSDefaultParameterValues["${n}:Credential"]     = $creds
            $global:PSDefaultParameterValues["${n}:AccountID"]      = $accountId
        }

        if (Test-HPCmdlet 'Set-ConnectionSettings') {
            try {
                Set-ConnectionSettings -Credential $creds -CredentialType $credType -AccountID $accountId
            } catch {
                try { Set-ConnectionSettings -Credential $creds -CredentialType $credType } catch { }
            }
        }
    } catch {
        Write-Warning "Could not seed HostPilot connection parameters: $($_.Exception.Message)"
    }
}

function Assert-HostPilotSession {
    if (-not (Test-HPCmdlet 'Get-User')) {
        throw ("HostPilot cmdlets not found. Launch the HostPilot PowerShell session " +
               "(dot-source Hosting.Powershell.ps1), log in, then run this script " +
               "from that window. See README.md.")
    }
    Ensure-HPConnection
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
    # Returns the first cmdlet name from the candidate list that exists in
    # this session, or $null. Local-only check (see Test-HPCmdlet).
    param([Parameter(Mandatory)][string[]]$Candidates)
    foreach ($name in $Candidates) {
        if (Test-HPCmdlet $name) { return $name }
    }
    return $null
}
