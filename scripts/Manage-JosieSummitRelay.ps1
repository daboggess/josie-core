[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('InitializeProfile', 'Probe', 'RunAcceptance')]
    [string]$Action
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Josie Python environment is unavailable.' }

$arguments = @('-m', 'josie.summit_browser', '--project-root', $projectRoot)
switch ($Action) {
    'InitializeProfile' { $arguments += '--initialize-profile' }
    'Probe' { }
    'RunAcceptance' { $arguments += '--acceptance' }
}
& $pythonPath @arguments
exit $LASTEXITCODE
