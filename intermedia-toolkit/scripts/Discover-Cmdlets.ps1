<#
.SYNOPSIS
  Dumps every HostPilot/Exchange cmdlet relevant to this toolkit, with its
  full syntax, to reference\cmdlet-syntax.txt.

.DESCRIPTION
  Run ONCE inside the connected HostPilot PowerShell session, then let Claude
  read reference\cmdlet-syntax.txt and align the other scripts with what your
  environment actually exposes.

  Output is built entirely in memory and written in a single operation —
  per-line appends get intermittently locked by OneDrive sync on synced paths.

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

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add("HostPilot PowerShell cmdlet inventory - generated $((Get-Date).ToString('o'))")
$lines.Add("Cmdlet count: $($cmds.Count)")
$lines.Add('')

# Quick index of all names first, so the file is useful even if Get-Help
# fails for some cmdlets.
$lines.Add('==== INDEX ====')
foreach ($c in $cmds) { $lines.Add($c.Name) }
$lines.Add('')

foreach ($c in $cmds) {
    $lines.Add("==== $($c.Name) ====")
    try {
        # Syntax block is compact and always available; -Detailed help can be
        # slow/unavailable over implicit remoting.
        $syntax = (Get-Command $c.Name -Syntax | Out-String).Trim()
        if ($syntax) { $lines.Add($syntax) }
        $help = (Get-Help $c.Name -ErrorAction SilentlyContinue | Out-String).Trim()
        if ($help) { $lines.Add($help) }
    } catch {
        $lines.Add("  (help/syntax unavailable: $($_.Exception.Message))")
    }
    $lines.Add('')
}

Set-Content -Path $outFile -Value $lines -Encoding UTF8

Write-Host "Wrote $($cmds.Count) cmdlet definitions to $outFile"
Write-Host "Next: open this folder in Claude Code and ask it to calibrate the scripts against the reference file."
