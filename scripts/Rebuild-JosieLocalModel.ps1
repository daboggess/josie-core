[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'Medium')]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
$ollamaPath = 'D:\Josie-Storage\apps\Ollama\0.32.5\ollama.exe'
$modelfile = Join-Path $projectRoot 'deploy\Josie.Modelfile'
$model = 'josie-local:1.0'
$rollbackModel = 'josie-local:pre-grounding'

foreach ($required in $ollamaPath, $modelfile) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Required local model file is missing: $required" }
}

& (Join-Path $PSScriptRoot 'Ensure-JosieOllama.ps1')
$modelsBefore = & $ollamaPath list
if ($LASTEXITCODE -ne 0 -or -not ($modelsBefore -match '^josie-local:1.0\s')) {
    throw 'The current Josie model is unavailable; refusing to rebuild without a rollback source.'
}

if (-not ($modelsBefore -match '^josie-local:pre-grounding\s')) {
    if ($PSCmdlet.ShouldProcess($rollbackModel, 'Create metadata-only rollback tag for the current model')) {
        & $ollamaPath cp $model $rollbackModel
        if ($LASTEXITCODE -ne 0) { throw 'The rollback model tag could not be created.' }
    }
}

if ($PSCmdlet.ShouldProcess($model, 'Rebuild the governed local model from the tracked Modelfile')) {
    & $ollamaPath create $model -f $modelfile
    if ($LASTEXITCODE -ne 0) { throw 'The governed Josie model could not be rebuilt.' }
}

$tool = [ordered]@{
    type = 'function'
    function = [ordered]@{
        name = 'record_review_proposal'
        description = 'Record a bounded local proposal for human review. Never executes an action.'
        parameters = [ordered]@{
            type = 'object'
            required = @('kind', 'summary')
            properties = [ordered]@{
                kind = @{ type = 'string'; enum = @('health_check', 'memory_export', 'restore_drill') }
                summary = @{ type = 'string' }
            }
        }
    }
}
$userMessage = @{ role = 'user'; content = 'Use record_review_proposal to record a health_check proposal saying phone test successful.' }
$firstPayload = @{
    model = $model
    stream = $false
    tools = @($tool)
    messages = @($userMessage)
    options = @{ temperature = 0; seed = 42; num_ctx = 2048; num_predict = 128 }
} | ConvertTo-Json -Depth 12
$first = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:11434/api/chat' `
    -ContentType 'application/json' -Body $firstPayload -TimeoutSec 180
$calls = @($first.message.tool_calls)
if ($calls.Count -ne 1 -or $calls[0].function.name -ne 'record_review_proposal') {
    throw 'Josie did not make the expected single bounded tool call.'
}
if ($calls[0].function.arguments.kind -ne 'health_check') {
    throw 'Josie selected an unexpected proposal kind during validation.'
}

$toolResult = @{
    status = 'review_required'
    proposal_id = 'validation-only'
    kind = 'health_check'
    actions_queued = 0
    actions_executed = 0
    duplicate = $false
    assistant_message = 'No action was performed. A health_check proposal was recorded for human review. Status: review_required. Actions queued: 0. Actions executed: 0.'
} | ConvertTo-Json -Compress
$secondPayload = @{
    model = $model
    stream = $false
    tools = @($tool)
    messages = @(
        $userMessage,
        $first.message,
        @{ role = 'tool'; tool_name = 'record_review_proposal'; content = $toolResult }
    )
    options = @{ temperature = 0; seed = 42; num_ctx = 2048; num_predict = 128 }
} | ConvertTo-Json -Depth 12
$second = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:11434/api/chat' `
    -ContentType 'application/json' -Body $secondPayload -TimeoutSec 180
$reply = [string]$second.message.content
$normalized = $reply.ToLowerInvariant()
$forbiddenClaims = @('20%', 'efficiency', 'according to the review', 'approved', 'completed')
$requiredClaims = @('review')
$zeroExecutionGrounded = $normalized -match 'actions queued: 0' -or
    $normalized -match 'no actions? (have been )?queued or executed' -or
    $normalized -match 'no action was performed'
if ([string]::IsNullOrWhiteSpace($reply) -or -not $zeroExecutionGrounded) {
    $preview = if ($reply.Length -gt 300) { $reply.Substring(0, 300) } else { $reply }
    throw "Josie did not ground its final reply in the zero-execution tool result. Observed: $preview"
}
foreach ($claim in $requiredClaims) {
    if (-not $normalized.Contains($claim)) { throw "Josie's tool reply omitted required evidence: $claim" }
}
foreach ($claim in $forbiddenClaims) {
    if ($normalized.Contains($claim)) { throw "Josie invented a forbidden post-tool claim: $claim" }
}

$modelsAfter = & $ollamaPath list
$modelLine = @($modelsAfter | Where-Object { $_ -match '^josie-local:1.0\s' })[0]
$parts = $modelLine -split '\s+'
[ordered]@{
    status = 'ready'
    model = $model
    observed_model_digest = if ($parts.Count -ge 2) { $parts[1] } else { $null }
    rollback_model = $rollbackModel
    expected_tool_call = $true
    grounded_tool_reply = $true
    invented_claims = $false
    cloud_activity = $false
    downloaded_model = $false
} | ConvertTo-Json -Depth 3
