<#
.SYNOPSIS
  Dumps every cmdlet relevant to this toolkit, with its parameter syntax, to
  reference\cmdlet-syntax.txt.

.DESCRIPTION
  Run ONCE inside the connected HostPilot PowerShell session, then let Claude
  read reference\cmdlet-syntax.txt and align the other scripts with what your
  environment actually exposes.

  DEX sessions use implicit remoting: cmdlets are local proxy functions for a
  remote Exchange endpoint. This script introspects those proxies entirely
  locally (ParameterSets), because per-cmdlet remote calls (Get-Help, or
  Get-Command -Syntax) both fail on proxies and can overload the WinRM
  channel. Output is built in memory and written once (OneDrive-synced paths
  intermittently lock per-line appends).

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

$lines.Add('==== INDEX ====')
foreach ($c in $cmds) { $lines.Add("$($c.Name)  [$($c.CommandType)]") }
$lines.Add('')

foreach ($c in $cmds) {
    $lines.Add("==== $($c.Name) ====")
    try {
        # ParameterSets are populated on the local proxy object - no remote call.
        $sets = @($c.ParameterSets)
        if ($sets.Count -gt 0) {
            foreach ($ps in $sets) {
                $lines.Add(("  {0} {1}" -f $c.Name, $ps.ToString()))
            }
        } elseif ($c.Definition) {
            $lines.Add(($c.Definition | Out-String).Trim())
        } else {
            $lines.Add('  (no local parameter metadata)')
        }
    } catch {
        $lines.Add("  (introspection failed: $($_.Exception.Message))")
    }
    $lines.Add('')
}

Set-Content -Path $outFile -Value $lines -Encoding UTF8

Write-Host "Wrote $($cmds.Count) cmdlet definitions to $outFile"
Write-Host "Next: open this folder in Claude Code and ask it to calibrate the scripts against the reference file."
