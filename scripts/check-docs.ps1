$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root

try {
    # Cached paths include unstaged deletions, so filter against the current
    # worktree before reading or reporting the checked file count.
    $files = @(
        git ls-files --cached --others --exclude-standard -- "*.md" |
            Where-Object { Test-Path -LiteralPath $_ -PathType Leaf }
    )
    $failed = $false
    $checkedLinks = 0
    $linkPattern = '!?\[[^\]]*\]\((?<target><[^>]+>|[^)\s]+)(?:\s+["''][^)]*["''])?\)'

    foreach ($file in $files) {
        $content = Get-Content -LiteralPath $file -Raw -Encoding utf8
        $fenceCount = @(
            Select-String -LiteralPath $file -Pattern '^\s*```'
        ).Count
        if (($fenceCount % 2) -ne 0) {
            Write-Error "Unbalanced Markdown code fences: $file"
            $failed = $true
        }

        foreach ($match in [regex]::Matches($content, $linkPattern)) {
            $target = $match.Groups["target"].Value.Trim("<", ">")
            if ($target -match '^(?:https?:|mailto:|data:|javascript:|#)') {
                continue
            }

            $pathPart = ($target -split "#", 2)[0]
            if ([string]::IsNullOrWhiteSpace($pathPart)) {
                continue
            }

            $pathPart = [uri]::UnescapeDataString($pathPart)
            $base = Split-Path -Parent $file
            if ([string]::IsNullOrEmpty($base)) {
                $base = "."
            }
            $resolved = Join-Path $base ($pathPart -replace "/", [IO.Path]::DirectorySeparatorChar)
            $checkedLinks++
            if (-not (Test-Path -LiteralPath $resolved)) {
                Write-Error "Broken local Markdown link: $file -> $target"
                $failed = $true
            }
        }
    }

    if ($failed) {
        exit 1
    }
    Write-Output "Markdown checks passed: $($files.Count) files, $checkedLinks local links."
}
finally {
    Pop-Location
}
