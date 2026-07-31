# Calibration record — DEX environment

Calibrated 2026-07-31 against live parameter sets captured from the connected
`[DEX]` HostPilot PowerShell session (dex.intermedia.net/powershell,
implicit remoting). This is the ground truth for cmdlet syntax in this
toolkit. Do not "fix" scripts back to guessed syntax — check here first.

## Environment facts

- Platform: **SEH** (shared hosted Exchange), endpoint
  `https://exchange.intermedia.net/powershell`. Confirmed by DNS:
  autodiscover CNAMEs to an `exchNNN.serverdata.net` shared cluster.
  (An earlier DEX login "succeeded" at connection level but every data
  cmdlet returned AccessDenied — auth is central, data is per-platform.
  Do not use dex.)
- Credential type: **User (U) ONLY**. Per Intermedia KB 12563,
  "Administrator type is used only by Intermedia Administrators" — an
  Administrator login connects but gets AccessDenied on every data cmdlet.
  The User login flow prompts for the numeric AccountID and registers it
  via Set-ConnectionSettings; cmdlets then need NO auth parameters.
  Passing -AccountID/-Credential per call is the KB 12323 "run as another
  account" override — avoid it.
- Launcher: dot-source `HostPilot.PowerShell\Scripts\Hosting.PowerShell.ps1`;
  platform `seh`; press Enter at the credential-type prompt (User is
  default). Never write the actual login address or AccountID into tracked
  files — this repo is public. The AccountID lives in
  reference/connection.local.json (gitignored), created on first script run.
- Credentials are cached after first login (`Clear-SavedHPCredential` resets).
- Cmdlets are implicit-remoting proxy functions. **Do not** run per-cmdlet
  `Get-Help`/`Get-Command -Syntax` loops against them — remote round-trips
  fail oddly ("Cannot find a provider with the name 'FileSystem'") and enough
  of them drop the WinRM session. Local `.ParameterSets` metadata is safe.
- If the session drops mid-run: close the whole PowerShell window and start a
  fresh one, then re-dot-source. Re-dot-sourcing in the same window fails with
  "The runspace state is not valid for this operation".
- `-CredentialType`, `-Credential`, `-AccountID` appear mandatory in every
  signature but are injected by the hosting shell — never pass them.
- 101 cmdlets total; full index in cmdlet-syntax.txt (regenerate with
  Discover-Cmdlets.ps1).

## Confirmed signatures (verbatim from ParameterSets)

```
Add-DistributionGroupMember    [-Identity] <ADObjectIDParameter> [[-OriginatingServer] <string>] [-Members] <ADObjectIDParameter[]> [-Force]
Remove-DistributionGroupMember [-Identity] <ADObjectIDParameter> [[-OriginatingServer] <string>] [-Members] <ADObjectIDParameter[]> [-Force] [-WhatIf] [-Confirm]
Get-DistributionGroupMember    [-Identity] <ADObjectIDParameter> [[-OriginatingServer] <string>] [-Force]
Grant-RecipientPermission      [-Identity] <ADObjectIDParameter> -Recipient <ADObjectIDParameter> -AccessRights <string> [-Force]
Revoke-RecipientPermission     [-Identity] <ADObjectIDParameter> -Recipient <ADObjectIDParameter> -AccessRights <string> [-Force]
Grant-ExchangeMailboxPermission [-Identity] <ADObjectIDParameter> -Recipients <ADObjectIDParameter[]> -AccessRights <string> [-Force]
New-User                       [-UserPrincipalName] <string> [[-Password] <securestring>] [-DisplayName] <string> [-AlternativeEmail <string>] [-Phone <string>] [-MobilePhone <string>] [-HomePhone <string>] [-Force]
Enable-ExchangeMailbox         [-Identity] <string> [-Force] [-WhatIf] [-Confirm]
Get-UserMemberOf               [-Identity] <ADObjectIDParameter> [-Force]
```

(Credential/AccountID params omitted above — shell-injected.)

## Connection/auth mechanism (from Hosting.Powershell.ps1 source)

- Login flow: `GetHPCred -plat <PLATFORM> -credentialType <type> -IgnoreExisting $true`
  → `ConnectHP` creates a PSSession named after the platform ("DEX")
  → `Import-PSSession -AllowClobber` → `Set-ConnectionSettings -Credential
  $creds -CredentialType <type>` (plus `-AccountID <id>` prompted only for
  credType "User"). Globals set: `$global:desc` = platform name,
  `$global:CredentialType`, `$global:UserNames[<plat>]`.
- Connection settings live in the REMOTE session. If it drops and implicit
  remoting rebuilds it, settings are lost → every cmdlet prompts for
  CredentialType/Credential/AccountID. Fix: `Ensure-HPConnection` in
  _Common.ps1 re-runs GetHPCred + Set-ConnectionSettings; it is called from
  Assert-HostPilotSession, i.e. at the start of every toolkit script.
- The imported remote module CLOBBERS `Get-Command`. Never call bare
  Get-Command in scripts — use `Test-Path function:\<name>` or
  `Microsoft.PowerShell.Core\Get-Command` (see Test-HPCmdlet).
- Saved credentials are stored in Windows Credential Manager via the
  hosting script's PsCredMan helper; `Clear-SavedHPCredential` resets.

## AccountID + prompt-stall hazard

- With an Administrator-type login, every data cmdlet requires `-AccountID`
  per call — the hosting script's login flow only registers it for the
  "User" credential type. An unseeded call makes PowerShell prompt for it
  interactively, and a prompt in the middle of a remote call stalls WinRM
  long enough to kill the session (HTTP error 12152).
- Fix: `Ensure-HPConnection` seeds `$PSDefaultParameterValues` with
  CredentialType/Credential/AccountID for every toolkit-used cmdlet (list in
  _Common.ps1) and also re-runs `Set-ConnectionSettings`. AccountID is cached
  in reference/connection.local.json after being asked once.

## Open items

- `-AccessRights` accepted string values are unverified; scripts default to
  `SendAs`. First real grant will confirm; if rejected, likely alternates:
  `Send-As`, `SendOnBehalf`. Record the working value here once known.
- Note `Grant-RecipientPermission` takes singular `-Recipient`;
  `Grant-ExchangeMailboxPermission` takes plural `-Recipients`.
- `Get-DistributionGroup` with no arguments: not yet verified whether it
  lists all DLs (Get-DLReport.ps1 assumes it does).

## Script-to-cmdlet map

| Script | Calls |
|---|---|
| Update-DLMembership.ps1 | Get-DistributionGroup, Add-DistributionGroupMember -Identity -Members, Remove-DistributionGroupMember -Identity -Members -Confirm:$false |
| Set-SendAsPermission.ps1 | Get-User, Grant/Revoke-RecipientPermission -Identity -Recipient -AccessRights |
| New-BulkUsers.ps1 | Get-User, New-User -UserPrincipalName -DisplayName, Enable-ExchangeMailbox -Identity -Confirm:$false |
| Get-DLReport.ps1 | Get-DistributionGroup, Get-DistributionGroupMember (discovered) |
