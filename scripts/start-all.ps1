param(
    [switch]$SkipRedis,
    [switch]$SkipOllama,
    [switch]$SkipFrontend,
    [switch]$SkipBackend,
    [switch]$SkipUserService,
    [switch]$NoReload,
    [int]$FrontendPort = 3000,
    [int]$BackendPort = 8000,
    [int]$UserPort = 8001
)

$ErrorActionPreference = "Stop"

function Write-Info($Message) {
    Write-Host "[INFO] $Message" -ForegroundColor Cyan
}

function Write-Warn($Message) {
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Write-Ok($Message) {
    Write-Host "[ OK ] $Message" -ForegroundColor Green
}

function Test-PortOpen([string]$HostName, [int]$Port) {
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $async = $client.BeginConnect($HostName, $Port, $null, $null)
        $success = $async.AsyncWaitHandle.WaitOne(500, $false)
        if ($success) {
            $client.EndConnect($async)
            $client.Close()
            return $true
        }
        $client.Close()
        return $false
    } catch {
        return $false
    }
}

function Find-CommandPath([string]$Name) {
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

function Start-ServiceWindow([string]$Title, [string]$WorkingDirectory, [string]$Command) {
    $escapedTitle = $Title.Replace('"', '\"')
    $escapedDir = $WorkingDirectory.Replace("'", "''")
    $fullCommand = "Set-Location -LiteralPath '$escapedDir'; `$Host.UI.RawUI.WindowTitle = '$escapedTitle'; $Command"
    Start-Process powershell.exe -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy", "Bypass",
        "-Command", $fullCommand
    ) -WorkingDirectory $WorkingDirectory
}

$Root = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $Root "backend"
$UserDir = Join-Path $Root "DjangoUserService"
$FrontDir = Join-Path $Root "front"

Write-Info "Project root: $Root"

if (-not (Test-Path $BackendDir)) { throw "backend directory not found: $BackendDir" }
if (-not (Test-Path $UserDir)) { throw "DjangoUserService directory not found: $UserDir" }
if (-not (Test-Path $FrontDir)) { throw "front directory not found: $FrontDir" }

Write-Info "Checking infrastructure ports..."

if (Test-PortOpen "127.0.0.1" 3306) {
    Write-Ok "MySQL looks reachable on 127.0.0.1:3306"
} else {
    Write-Warn "MySQL is not reachable on 127.0.0.1:3306. Please start MySQL first, for example: net start mysql"
}

if (-not $SkipRedis) {
    if (Test-PortOpen "127.0.0.1" 6379) {
        Write-Ok "Redis already running on 127.0.0.1:6379"
    } else {
        $redisServer = Find-CommandPath "redis-server"
        if ($redisServer) {
            Write-Info "Starting Redis..."
            Start-ServiceWindow "RAG Redis" $Root "redis-server"
        } else {
            Write-Warn "redis-server was not found. Start Redis manually, or rerun with -SkipRedis."
        }
    }
}

if (-not $SkipOllama) {
    if (Test-PortOpen "127.0.0.1" 11434) {
        Write-Ok "Ollama already running on 127.0.0.1:11434"
    } else {
        $ollama = Find-CommandPath "ollama"
        if ($ollama) {
            Write-Info "Starting Ollama..."
            Start-ServiceWindow "RAG Ollama" $Root "ollama serve"
        } else {
            Write-Warn "ollama was not found. Skip if you only use cloud or OpenAI-compatible models."
        }
    }
}

if (-not $SkipUserService) {
    if (Test-PortOpen "127.0.0.1" $UserPort) {
        Write-Ok "Django user service already running on 127.0.0.1:$UserPort"
    } else {
        Write-Info "Starting Django user service..."
        Start-ServiceWindow "RAG Django User Service" $UserDir "uv run python manage.py runserver 127.0.0.1:$UserPort"
    }
}

if (-not $SkipBackend) {
    if (Test-PortOpen "127.0.0.1" $BackendPort) {
        Write-Ok "FastAPI backend already running on 127.0.0.1:$BackendPort"
    } else {
        $reloadFlag = if ($NoReload) { "" } else { " --reload" }
        Write-Info "Starting FastAPI backend..."
        Start-ServiceWindow "RAG FastAPI Backend" $BackendDir "uv run uvicorn main:app --host 127.0.0.1 --port $BackendPort$reloadFlag"
    }
}

if (-not $SkipFrontend) {
    if (Test-PortOpen "127.0.0.1" $FrontendPort) {
        Write-Ok "Frontend already running on 127.0.0.1:$FrontendPort"
    } else {
        Write-Info "Starting React frontend..."
        Start-ServiceWindow "RAG React Frontend" $FrontDir "npm run dev -- --host 0.0.0.0 --port $FrontendPort"
    }
}

Write-Host ""
Write-Ok "Startup commands have been dispatched."
Write-Host ""
Write-Host "Open these URLs:" -ForegroundColor Cyan
Write-Host "  Frontend:     http://127.0.0.1:$FrontendPort"
Write-Host "  FastAPI docs: http://127.0.0.1:$BackendPort/docs"
Write-Host "  Django docs:  http://127.0.0.1:$UserPort/docs/"
Write-Host ""
Write-Host "Tips:" -ForegroundColor Cyan
Write-Host "  - Keep the opened PowerShell windows running."
Write-Host "  - Restart this script after changing front/vite.config.ts."
Write-Host "  - If Redis/Ollama/MySQL are installed as services, starting them manually as services is also fine."
