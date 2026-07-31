<#
.SYNOPSIS
  Audit report: dumps all distribution lists (and their members, where the
  session exposes a member cmdlet) to reference\dl-report.csv. Read-only.

.EXAMPLE
  .\Get-DLReport.ps1

.EXAMPLE
  .\Get-DLReport.ps1 -DistributionList sales@yourdomain.com
#>
[CmdletBinding()]
param(
    [string]$DistributionList
)

. "$PSScriptRoot\_Common.ps1"
Assert-HostPilotSession

$outDir = Join-Path $script:ToolkitRoot 'reference'
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir | Out-Null }
$outFile = Join-Path $outDir 'dl-report.csv'

if ($DistributionList) {
    $dls = @(Get-DistributionGroup $DistributionList)
    if (-not $dls) { throw "Distribution list not found: $DistributionList" }
} else {
    $dls = @(Get-DistributionGroup)
}

# Member enumeration cmdlet name isn't publicly documented; discover it.
$memberCmd = Find-FirstCmdlet -Candidates @('Get-DistributionGroupMember', 'Get-DistributionGroupMembers')

$rows = foreach ($dl in $dls) {
    $dlName = if ($dl.PSObject.Properties['EmailAddress']) { $dl.EmailAddress }
              elseif ($dl.PSObject.Properties['DisplayName']) { $dl.DisplayName }
              else { "$dl" }
    if ($memberCmd) {
        $members = @()
        try { $members = @(& $memberCmd $dlName) } catch { }
        if ($members.Count -eq 0) {
            [pscustomobject]@{ DistributionList = $dlName; Member = '(none or not readable)' }
        } else {
            foreach ($m in $members) {
                $mName = if ($m.PSObject.Properties['EmailAddress']) { $m.EmailAddress }
                         elseif ($m.PSObject.Properties['DisplayName']) { $m.DisplayName }
                         else { "$m" }
                [pscustomobject]@{ DistributionList = $dlName; Member = $mName }
            }
        }
    } else {
        [pscustomobject]@{ DistributionList = $dlName; Member = '(no member cmdlet found - run Discover-Cmdlets.ps1)' }
    }
}

$rows | Export-Csv -Path $outFile -NoTypeInformation
$rows | Format-Table -AutoSize
Write-Host ("Wrote {0} rows for {1} distribution list(s) to {2}" -f @($rows).Count, @($dls).Count, $outFile)
if (-not $memberCmd) {
    Write-Host 'NOTE: no member-enumeration cmdlet found. Run Discover-Cmdlets.ps1 so Claude can recalibrate.'
}
