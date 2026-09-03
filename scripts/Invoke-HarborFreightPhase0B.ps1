[CmdletBinding()]
param(
    [switch]$SystemInventory,
    [switch]$WriteRestoreTest,
    [string]$ReceiptPath
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$manifest = Join-Path $repo 'config/harbor-freight-backup-manifest.json'
$results = [System.Collections.Generic.List[object]]::new()
function Add-Result($Id, $Status, $Detail) {
    $results.Add([ordered]@{ id=$Id; status=$Status; detail=$Detail })
}
try {
    $parsed = Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json
    if ($parsed.schema_version -ne 1 -or @($parsed.entries).Count -eq 0) { throw 'Unsupported or empty manifest' }
    Add-Result 'manifest' 'PASS' "Parsed $(@($parsed.entries).Count) entries"
} catch { Add-Result 'manifest' 'FAIL' $_.Exception.Message }

if ($SystemInventory) {
    foreach ($tool in 'git','docker','wsl','sqlite3') {
        $found = Get-Command $tool -ErrorAction SilentlyContinue
        Add-Result "tool-$tool" $(if ($found) {'PASS'} else {'NEEDS_DUSTIN'}) $(if ($found) {$found.Source} else {'not found'})
    }
    Add-Result 'physical-storage' 'NEEDS_DUSTIN' 'Confirm drive mapping, encrypted off-device target, and recovery media physically.'
    Add-Result 'service-volume-health' 'NEEDS_DUSTIN' 'Inventory does not inspect service, container, volume, database, or secret contents.'
} else {
    Add-Result 'system-inventory' 'SKIPPED' 'Use -SystemInventory for read-only host/tool inventory.'
}

if ($WriteRestoreTest) {
    $fixtureRoot = Join-Path ([IO.Path]::GetTempPath()) ("josie-phase0b-" + [guid]::NewGuid())
    try {
        New-Item -ItemType Directory -Path $fixtureRoot | Out-Null
        $python = Join-Path $repo '.venv/Scripts/python.exe'
        if (-not (Test-Path -LiteralPath $python)) { throw 'Repository Python runtime not found' }
        $code = "from pathlib import Path; import json; from josie.harbor_freight_phase0b import run_fixture; print(json.dumps(run_fixture(Path(r'$($fixtureRoot.Replace("'","''"))'))))"
        $output = & $python -c $code
        if ($LASTEXITCODE -ne 0) { throw 'Fixture process failed' }
        $fixture = $output | ConvertFrom-Json
        Add-Result 'isolated-restore-fixture' $fixture.status "Verified $(@($fixture.checksums.psobject.Properties).Count) SHA-256 checksums; temporary content cleaned"
    } catch { Add-Result 'isolated-restore-fixture' 'FAIL' $_.Exception.Message }
    finally {
        if ($fixtureRoot -and (Test-Path -LiteralPath $fixtureRoot)) { Remove-Item -LiteralPath $fixtureRoot -Recurse -Force }
    }
} else {
    Add-Result 'isolated-restore-fixture' 'SKIPPED' 'Use -WriteRestoreTest to create and clean an isolated temporary fixture.'
}

$receipt = [ordered]@{
    schema_version=1; generated_utc=[DateTime]::UtcNow.ToString('o'); mode=$(if ($WriteRestoreTest) {'isolated-write-test'} elseif ($SystemInventory) {'read-only-inventory'} else {'dry-run'})
    production_changed=$false; external_write=$false; results=$results
}
$json = $receipt | ConvertTo-Json -Depth 6
if ($ReceiptPath) {
    if (-not $WriteRestoreTest) { throw '-ReceiptPath requires -WriteRestoreTest so default dry-run remains write-free.' }
    $resolvedParent = Split-Path -Parent $ReceiptPath
    if (-not $resolvedParent) { $resolvedParent = (Get-Location).Path }
    if (-not (Test-Path -LiteralPath $resolvedParent)) { throw 'Receipt parent directory does not exist.' }
    [IO.File]::WriteAllText($ReceiptPath, $json, [Text.UTF8Encoding]::new($false))
}
$json
if (@($results | Where-Object status -eq 'FAIL').Count) { exit 1 }
