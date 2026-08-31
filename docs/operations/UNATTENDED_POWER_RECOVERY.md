# Unattended Power Recovery

Status: `STAGED / ATTENDED CREDENTIAL AND BIOS GATES REMAIN`

Goal: after utility power returns, Josie powers on, creates the Windows user
session required by Docker Desktop, restores all local services, and locks the
workstation again without waiting for Dustin.

## Implemented remotely

- Microsoft Sysinternals Autologon 3.10 was downloaded from Microsoft's
  official Sysinternals endpoint to `D:\Josie-Storage\apps\Sysinternals`.
- The Authenticode signature was verified as valid and issued to Microsoft
  Corporation.
- The enable workflow accepts no password parameter and launches only the
  attended Microsoft GUI.
- A two-minute post-boot automatic workstation lock is staged.
- UAC must remain enabled.
- Plaintext `DefaultPassword` storage is rejected.
- A read-only status command and attended disable/reversal workflow are staged.

Autologon is not enabled yet. No password was requested, received, logged, or
placed on a command line.

## Remaining attended gates

1. Verify BitLocker protection on C: or explicitly accept the physical-access
   risk if the drive is not protected.
2. Run `scripts\Enable-JosieUnattendedRecovery.ps1` as administrator.
3. Enter the real Windows account password directly into Microsoft's Autologon
   dialog and click **Enable**. A Windows Hello PIN is not the account password.
4. Verify the AIMB-205G2 firmware setting for restoration after AC power loss is
   set to **Power On**. Historical unexpected-shutdown events prove later boots,
   but do not prove the firmware powered on without a person.
5. Perform one attended AC-loss recovery test and verify the new startup proof,
   automatic re-lock, services, firewall, and private phone access.

Microsoft warns that although Autologon stores the credential as an LSA secret,
a local administrator can retrieve and decrypt it. This is an accepted tradeoff
only after Dustin completes the attended enable gate.

## Read-only status

`powershell -NoProfile -File scripts\Get-JosieUnattendedRecoveryStatus.ps1`

## Reversal

Run `scripts\Disable-JosieUnattendedRecovery.ps1` as administrator, click
**Disable** in Microsoft's dialog, and confirm the reported disabled state.
