param([switch]$UseExistingTamperedCopies)

$ErrorActionPreference = "Stop"

$tamperRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$artifactRoot = (Resolve-Path -LiteralPath (Join-Path $tamperRoot "..")).Path
$repoRoot = (Get-Item -LiteralPath $tamperRoot).Parent.Parent.Parent.Parent.FullName
$sourceStorage = Join-Path $artifactRoot "backups\storage-bundle"
$sourceChroma = Join-Path $artifactRoot "backups\chroma-bundle"
$storageBundle = Join-Path $tamperRoot "storage-bundle-tampered"
$chromaBundle = Join-Path $tamperRoot "chroma-bundle-tampered"
$storageTarget = Join-Path $tamperRoot "storage-restore-must-not-exist"
$chromaTarget = Join-Path $tamperRoot "chroma-restore-must-not-exist"
$logsRoot = Join-Path $tamperRoot "logs"
$tamperHash = "9E004D2C11FE83A9F89FBC7097A3C34A07D55E9E7D59D329D2B0CFBF142C832D"

foreach ($required in @($sourceStorage, $sourceChroma)) {
    if (-not (Test-Path -LiteralPath $required -PathType Container)) {
        throw "Required source bundle is missing: $required"
    }
}
foreach ($freshTarget in @($storageTarget, $chromaTarget)) {
    if (Test-Path -LiteralPath $freshTarget) {
        throw "Fresh restore target already exists: $freshTarget"
    }
}

New-Item -ItemType Directory -Path $logsRoot -Force | Out-Null
$storageTamperFile = Join-Path $storageBundle "payload\objects\e1-synthetic-package.bin"
$chromaTamperFile = Join-Path $chromaBundle "payload\a0c914d7-d490-46f2-9a07-95d99074d95e\header.bin"
$storageSourceFile = Join-Path $sourceStorage "payload\objects\e1-synthetic-package.bin"
$chromaSourceFile = Join-Path $sourceChroma "payload\a0c914d7-d490-46f2-9a07-95d99074d95e\header.bin"
$storageBefore = (Get-FileHash -LiteralPath $storageSourceFile -Algorithm SHA256).Hash
$chromaBefore = (Get-FileHash -LiteralPath $chromaSourceFile -Algorithm SHA256).Hash

if ($UseExistingTamperedCopies) {
    foreach ($copy in @($storageBundle, $chromaBundle)) {
        if (-not (Test-Path -LiteralPath $copy -PathType Container)) {
            throw "Expected interrupted-run copy is missing: $copy"
        }
    }
} else {
    foreach ($copy in @($storageBundle, $chromaBundle)) {
        if (Test-Path -LiteralPath $copy) {
            throw "Refusing to overwrite existing evidence path: $copy"
        }
    }
    Copy-Item -LiteralPath $sourceStorage -Destination $storageBundle -Recurse
    Copy-Item -LiteralPath $sourceChroma -Destination $chromaBundle -Recurse
    Set-Content -LiteralPath $storageTamperFile -Value "E1-TAMPERED-BYTEST" -Encoding ascii -NoNewline
    Set-Content -LiteralPath $chromaTamperFile -Value "E1-TAMPERED-BYTEST" -Encoding ascii -NoNewline
}

$storageAfter = (Get-FileHash -LiteralPath $storageTamperFile -Algorithm SHA256).Hash
$chromaAfter = (Get-FileHash -LiteralPath $chromaTamperFile -Algorithm SHA256).Hash
if ($storageAfter -ne $tamperHash -or $chromaAfter -ne $tamperHash) {
    throw "Existing copies do not contain the expected fixed tamper marker"
}
if ((Get-FileHash -LiteralPath (Join-Path $sourceStorage "manifest.json") -Algorithm SHA256).Hash -ne
    (Get-FileHash -LiteralPath (Join-Path $storageBundle "manifest.json") -Algorithm SHA256).Hash) {
    throw "Storage manifest copy differs from its source"
}
if ((Get-FileHash -LiteralPath (Join-Path $sourceChroma "manifest.json") -Algorithm SHA256).Hash -ne
    (Get-FileHash -LiteralPath (Join-Path $chromaBundle "manifest.json") -Algorithm SHA256).Hash) {
    throw "Chroma manifest copy differs from its source"
}

function Invoke-RestoreAttempt {
    param(
        [string]$Name,
        [string]$Bundle,
        [string]$Target,
        [string]$TamperFile,
        [string]$HashBefore,
        [string]$HashAfter,
        [string]$LogPath
    )

    $output = @()
    $exitCode = 0
    Push-Location (Join-Path $repoRoot "backend")
    try {
        $arguments = "uv run python scripts/backup_restore.py restore --bundle `"$Bundle`" --target `"$Target`" 2>&1"
        $output = @(& cmd.exe /d /c $arguments)
        $exitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    $targetExists = Test-Path -LiteralPath $Target
    $targetEntries = if ($targetExists -and (Get-Item -LiteralPath $Target).PSIsContainer) {
        @(Get-ChildItem -LiteralPath $Target -Recurse -Force | ForEach-Object { $_.FullName })
    } else {
        @()
    }
    $log = @(
        "case=$Name"
        "bundle=$Bundle"
        "tampered_file=$TamperFile"
        "sha256_before=$HashBefore"
        "sha256_after=$HashAfter"
        "restore_exit_code=$exitCode"
        "restore_output_begin"
        $output
        "restore_output_end"
        "fresh_target_exists=$targetExists"
        "fresh_target_entries=$($targetEntries.Count)"
    )
    Set-Content -LiteralPath $LogPath -Value $log -Encoding utf8
    if ($exitCode -eq 0) {
        throw "$Name unexpectedly restored successfully"
    }
    if (($output -join "`n") -notmatch "backup payload does not match manifest") {
        throw "$Name failed for an unexpected reason"
    }
    if ($targetExists) {
        throw "$Name created the fresh target after rejecting the tampered bundle"
    }
}

Invoke-RestoreAttempt -Name "storage" -Bundle $storageBundle -Target $storageTarget `
    -TamperFile $storageTamperFile -HashBefore $storageBefore -HashAfter $storageAfter `
    -LogPath (Join-Path $logsRoot "storage-tamper-restore.txt")
Invoke-RestoreAttempt -Name "chroma" -Bundle $chromaBundle -Target $chromaTarget `
    -TamperFile $chromaTamperFile -HashBefore $chromaBefore -HashAfter $chromaAfter `
    -LogPath (Join-Path $logsRoot "chroma-tamper-restore.txt")

Set-Content -LiteralPath (Join-Path $logsRoot "summary.txt") -Value @(
    "storage_restore_rejected=true"
    "storage_fresh_target_exists=$(Test-Path -LiteralPath $storageTarget)"
    "chroma_restore_rejected=true"
    "chroma_fresh_target_exists=$(Test-Path -LiteralPath $chromaTarget)"
) -Encoding utf8
Write-Output "tamper rejection evidence complete: $tamperRoot"
