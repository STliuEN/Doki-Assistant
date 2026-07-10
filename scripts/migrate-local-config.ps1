$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$configDir = Join-Path $root "backend/app/config"

$legacySecurity = Join-Path $configDir "security.yaml"
$exampleSecurity = Join-Path $configDir "security.example.yaml"
$localSecurity = Join-Path $configDir "security.local.yaml"
if ((Test-Path -LiteralPath $legacySecurity) -and -not (Test-Path -LiteralPath $localSecurity)) {
    Copy-Item -LiteralPath $legacySecurity -Destination $localSecurity
    Write-Output "Created backend/app/config/security.local.yaml from the legacy config."
}
elseif ((Test-Path -LiteralPath $exampleSecurity) -and -not (Test-Path -LiteralPath $localSecurity)) {
    Copy-Item -LiteralPath $exampleSecurity -Destination $localSecurity
    Write-Output "Created backend/app/config/security.local.yaml from the example config."
}

$legacyMcp = Join-Path $configDir "mcp.yaml"
$exampleMcp = Join-Path $configDir "mcp.example.yaml"
$localMcp = Join-Path $configDir "mcp.local.yaml"
if ((Test-Path -LiteralPath $legacyMcp) -and -not (Test-Path -LiteralPath $localMcp)) {
    Copy-Item -LiteralPath $legacyMcp -Destination $localMcp
    Write-Output "Created backend/app/config/mcp.local.yaml from the legacy config."
}
elseif ((Test-Path -LiteralPath $exampleMcp) -and -not (Test-Path -LiteralPath $localMcp)) {
    Copy-Item -LiteralPath $exampleMcp -Destination $localMcp
    Write-Output "Created backend/app/config/mcp.local.yaml from the example config."
}

$envPath = Join-Path $root "backend/.env"
if (Test-Path -LiteralPath $envPath) {
    $lines = [IO.File]::ReadAllLines($envPath)
    $hasModelKey = $lines | Where-Object { $_ -match '^\s*MODEL_CONFIG_ENCRYPTION_KEY\s*=' }
    if (-not $hasModelKey) {
        $secretLine = $lines | Where-Object { $_ -match '^\s*SECRET_KEY\s*=' } | Select-Object -First 1
        if ($secretLine) {
            $secretValue = ($secretLine -split '=', 2)[1]
            $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
            $content = [IO.File]::ReadAllText($envPath).TrimEnd("`r", "`n")
            $content += "`r`nMODEL_CONFIG_ENCRYPTION_KEY=$secretValue`r`n"
            [IO.File]::WriteAllText($envPath, $content, $utf8NoBom)
            Write-Output "Initialized MODEL_CONFIG_ENCRYPTION_KEY from the current SECRET_KEY."
        }
        else {
            Write-Warning "backend/.env has no SECRET_KEY; MODEL_CONFIG_ENCRYPTION_KEY was not initialized."
        }
    }
}
else {
    Write-Warning "backend/.env does not exist; create it from backend/.env.example before startup."
}
