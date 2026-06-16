param(
    [switch]$SkipModelCheck
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$backendDir = Join-Path $repoRoot "backend"
$venvDir = Join-Path $backendDir ".venv"
$modelDir = Join-Path $backendDir "models\qwen3-reranker-4b"

Write-Host "Backend: $backendDir"

if (-not $SkipModelCheck) {
    $requiredFiles = @(
        "config.json",
        "modules.json",
        "config_sentence_transformers.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "model-00001-of-00002.safetensors",
        "model-00002-of-00002.safetensors",
        "model.safetensors.index.json",
        "1_LogitScore\config.json"
    )

    foreach ($file in $requiredFiles) {
        $path = Join-Path $modelDir $file
        if (-not (Test-Path -LiteralPath $path)) {
            throw "Qwen3-Reranker-4B 文件缺失: $path"
        }
    }

    Write-Host "Qwen3-Reranker-4B 文件检查通过: $modelDir"
}

Push-Location $backendDir
try {
    if (Test-Path -LiteralPath $venvDir) {
        $answer = Read-Host "将删除并重建 backend\.venv，继续吗？输入 YES 确认"
        if ($answer -ne "YES") {
            Write-Host "已取消。"
            exit 1
        }
        Remove-Item -LiteralPath $venvDir -Recurse -Force
    }

    uv sync
    uv run python -c "import torch; print('torch=', torch.__version__); print('cuda_available=', torch.cuda.is_available()); print('arch_list=', torch.cuda.get_arch_list() if torch.cuda.is_available() else [])"
}
finally {
    Pop-Location
}
