[CmdletBinding()]
param(
    [ValidateSet('DryRun','Inventory','VerifyFixture')]
    [string]$Mode = 'DryRun',
    [switch]$AllowTemporaryWrite,
    [string]$ReceiptPath
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $repo '.venv\Scripts\python.exe'
$manifest = Join-Path $repo 'config\harbor-freight-backup-manifest.json'
$temporaryRoot = Join-Path $repo '.harbor-freight-phase0b-temp'

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    Write-Error 'Repository Python runtime not found.'
    exit 2
}

if ($Mode -eq 'DryRun') {
    if ($AllowTemporaryWrite -or $ReceiptPath) {
        Write-Error 'DryRun refuses write switches and receipt paths.'
        exit 2
    }
    & $python -m josie.harbor_freight_phase0b --mode DryRun --manifest $manifest
    exit $LASTEXITCODE
}

if ($Mode -eq 'Inventory') {
    if ($AllowTemporaryWrite -or $ReceiptPath) {
        Write-Error 'Inventory is read-only and refuses write switches and receipt paths.'
        exit 2
    }
    $baseJson = & $python -m josie.harbor_freight_phase0b --mode DryRun --manifest $manifest
    if ($LASTEXITCODE -ne 0) { $baseJson; exit $LASTEXITCODE }
    $base = $baseJson | ConvertFrom-Json
    $results = [System.Collections.Generic.List[object]]::new()
    foreach ($item in $base.results) { $results.Add($item) }
    try {
        $logical = @(Get-CimInstance Win32_LogicalDisk | Select-Object DeviceID, DriveType, FileSystem, Size, FreeSpace)
        $physical = @(Get-CimInstance Win32_DiskDrive | Select-Object Index, Model, InterfaceType, Size, SerialNumber)
        $results.Add([ordered]@{id='drive_inventory';status='PASS';evidence=@{logical=$logical;physical=$physical;read_only=$true}})
    } catch {
        $results.Add([ordered]@{id='drive_inventory';status='NEEDS_DUSTIN';evidence=@{reason=$_.Exception.Message;read_only=$true}})
    }
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if ($docker) {
        $version = @(& docker version --format '{{.Client.Version}}' 2>$null)
        $volumes = @(& docker volume ls --format '{{.Name}}' 2>$null)
        $dockerStatus = if ($LASTEXITCODE -eq 0) { 'PASS' } else { 'NEEDS_DUSTIN' }
        $results.Add([ordered]@{id='docker_metadata';status=$dockerStatus;evidence=@{available=$true;client_version=($version -join '');volume_names=$volumes;contents_accessed=$false}})
    } else {
        $results.Add([ordered]@{id='docker_metadata';status='SKIPPED';evidence=@{available=$false;contents_accessed=$false}})
    }
    $cmdkey = Get-Command cmdkey.exe -ErrorAction SilentlyContinue
    $results.Add([ordered]@{id='credential_manager';status=$(if ($cmdkey){'PASS'}else{'NEEDS_DUSTIN'});evidence=@{command_accessible=[bool]$cmdkey;credential_values_accessed=$false;credential_list_accessed=$false}})
    try {
        $head = (& git -C $repo rev-parse HEAD).Trim()
        $branch = (& git -C $repo branch --show-current).Trim()
        $remotes = @(& git -C $repo remote)
        $results.Add([ordered]@{id='git_recovery';status='PASS';evidence=@{commit=$head;branch=$branch;remote_names=$remotes;remote_urls_accessed=$false}})
    } catch {
        $results.Add([ordered]@{id='git_recovery';status='NEEDS_DUSTIN';evidence=@{reason=$_.Exception.Message}})
    }
    $results.Add([ordered]@{id='physical_and_offsite_attestation';status='NEEDS_DUSTIN';evidence=@{reason='Physical drive mapping, encrypted off-device target, credential recoverability, and recovery media require attended confirmation.'}})
    [ordered]@{schema_version=1;mode='Inventory';status='PASS';production_changed=$false;external_write=$false;results=$results} | ConvertTo-Json -Depth 8
    exit 0
}

if (-not $AllowTemporaryWrite) {
    Write-Error 'VerifyFixture requires -AllowTemporaryWrite.'
    exit 2
}
$runId = [guid]::NewGuid().ToString('N')
$target = Join-Path $temporaryRoot ("fixture-" + $runId)
if (-not $ReceiptPath) { $ReceiptPath = Join-Path $temporaryRoot ("receipt-" + $runId + '.json') }
$fullReceipt = [IO.Path]::GetFullPath($ReceiptPath)
$fullTemporaryRoot = [IO.Path]::GetFullPath($temporaryRoot).TrimEnd('\') + '\'
if (-not $fullReceipt.StartsWith($fullTemporaryRoot, [StringComparison]::OrdinalIgnoreCase)) {
    Write-Error 'VerifyFixture receipt must remain under D:\Josie\.harbor-freight-phase0b-temp.'
    exit 2
}
& $python -m josie.harbor_freight_phase0b --mode VerifyFixture --manifest $manifest --allow-temporary-write --allowed-root $temporaryRoot --target $target --receipt $fullReceipt
exit $LASTEXITCODE
