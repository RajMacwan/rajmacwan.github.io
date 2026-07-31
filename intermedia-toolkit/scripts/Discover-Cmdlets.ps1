<#
.SYNOPSIS
  Dumps every HostPilot cmdlet relevant to this toolkit, with its full syntax,
  to reference\cmdlet-syntax.txt.

.DESCRIPTION
  Intermedia's public KB is bot-blocked, so the exact parameter names of some
  cmdlets could not be verified when this toolkit was written. Run this ONCE
  inside HostPilot PowerShell after logging in, then let Claude read
  reference\cmdlet-syntax.txt and align the other scripts with what your
  account's build actually exposes.

.EXAMPLE
  .\Discover-Cmdlets.ps1
#>
[CmdletBinding()]
param()

. "$PSScriptRoot\_Common.ps1"
Assert-HostPilotSession

$outDir = Join-Path $script:ToolkitRoot 'reference'
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir | Out-Null }
$outFile = Join-Path $outDir 'cmdlet-syntax.txt'

$patterns = @(
    '*User*', '*Mailbox*', '*DistributionGroup*', '*RecipientPermission*',
    '*EmailAddress*', '*Contact*', '*Domain*', '*AdSync*', '*ActiveSync*',
    '*OrganizationalUnit*', '*PublicFolder*', '*Permission*'
)

$cmds = foreach ($p in $patterns) { Get-Command $p -ErrorAction SilentlyContinue }
$cmds = $cmds | Sort-Object Name -Unique

"HostPilot PowerShell cmdlet inventory - generated $((Get-Date).ToString('o'))" | Set-Content $outFile
"Cmdlet count: $($cmds.Count)" | Add-Content $outFile
'' | Add-Content $outFile

foreach ($c in $cmds) {
    "==== $($c.Name) ====" | Add-Content $outFile
    try {
        (Get-Help $c.Name -Detailed | Out-String) | Add-Content $outFile
    } catch {
        "  (Get-Help failed: $($_.Exception.Message))" | Add-Content $outFile
    }
    '' | Add-Content $outFile
}

Write-Host "Wrote $($cmds.Count) cmdlet definitions to $outFile"
Write-Host "Next: open this folder in Claude Code and ask it to calibrate the scripts against the reference file."
