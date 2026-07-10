param(
    [switch]$Check
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$projects = @(
    "backend",
    "DjangoUserService"
)
$header = @(
    "# Generated from pyproject.toml and uv.lock by scripts/export-requirements.ps1.",
    "# Do not edit manually.",
    ""
) -join "`n"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$hasDrift = $false

foreach ($project in $projects) {
    $projectDir = Join-Path $root $project
    $target = Join-Path $projectDir "requirements.txt"
    $temporary = [IO.Path]::GetTempFileName()

    try {
        Push-Location $projectDir
        try {
            & uv export --quiet --no-cache --frozen --no-dev --no-emit-project --no-hashes --no-header --output-file $temporary
            if ($LASTEXITCODE -ne 0) {
                throw "uv export failed for $project"
            }
        }
        finally {
            Pop-Location
        }

        $body = [IO.File]::ReadAllText($temporary).Replace("`r`n", "`n")
        $generated = $header + $body

        if ($Check) {
            $current = if (Test-Path -LiteralPath $target) {
                [IO.File]::ReadAllText($target).Replace("`r`n", "`n")
            }
            else {
                ""
            }
            if ($current -cne $generated) {
                Write-Error "Generated requirements drift detected: $project/requirements.txt"
                $hasDrift = $true
            }
        }
        else {
            [IO.File]::WriteAllText($target, $generated, $utf8NoBom)
            Write-Output "Updated $project/requirements.txt"
        }
    }
    finally {
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
    }
}

if ($hasDrift) {
    exit 1
}
