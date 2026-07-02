param(
    [switch]$SkipRedis,
    [switch]$SkipOllama,
    [switch]$SkipFrontend,
    [switch]$SkipBackend,
    [switch]$SkipUserService,
    [switch]$NoReload,
    [int]$FrontendPort = 18080,
    [int]$BackendPort = 18000,
    [int]$UserPort = 18001,
    [int]$RedisPort = 18020,
    [int]$WaitTimeoutSeconds = 90,
    # 启动模式：
    #   Terminal = 所有服务进同一个 Windows Terminal 窗口的多个 Tab（默认，更整洁）
    #   Window   = 每个服务一个独立 PowerShell 窗口（旧行为，作为回退）
    # 选 Terminal 但找不到 wt.exe 时会自动降级为 Window。
    [ValidateSet('Terminal', 'Window')]
    [string]$Mode = 'Terminal'
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

function Wait-PortOpen([string]$ServiceName, [string]$HostName, [int]$Port, [int]$TimeoutSeconds) {
    # 阶梯启动的核心：在拉起下一个服务前，先轮询等待当前服务端口真正可连，
    # 避免“窗口都弹出来了但服务还没就绪”导致的交叉调用偶发失败。
    Write-Info "Waiting for $ServiceName on ${HostName}:${Port} (timeout ${TimeoutSeconds}s)..."
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-PortOpen $HostName $Port) {
            Write-Ok "$ServiceName is ready on ${HostName}:${Port}"
            return $true
        }
        Start-Sleep -Milliseconds 750
    }
    Write-Warn "$ServiceName did not become ready on ${HostName}:${Port} within ${TimeoutSeconds}s. Continuing anyway; check its window for errors."
    return $false
}

function Find-CommandPath([string]$Name) {
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

function Find-NpmCommand() {
    $npm = Find-CommandPath "npm.cmd"
    if (-not $npm) { $npm = Find-CommandPath "npm" }
    if ($npm) { return $npm }

    $candidates = @(
        "C:\nvm4w\nodejs\npm.cmd",
        "$env:ProgramFiles\nodejs\npm.cmd"
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return $candidate
        }
    }
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

function Find-WindowsTerminal() {
    $wt = Find-CommandPath "wt.exe"
    if ($wt) { return $wt }
    $alias = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps\wt.exe"
    if (Test-Path -LiteralPath $alias) { return $alias }
    return $null
}

# Windows Terminal 窗口名：所有服务的 Tab 都汇入同一个窗口。
$Script:WtWindowName = "doki-dev"
$Script:WtFirstTab = $true

function Start-ServiceTab([string]$WtPath, [string]$Title, [string]$WorkingDirectory, [string]$Command) {
    # 在名为 doki-dev 的窗口里新开一个 Tab；首个 Tab 负责建立/聚焦该窗口，
    # 之后的调用复用同一窗口追加 Tab，从而所有服务集中在一个窗口里。
    # 注意：wt 会把命令行里的分号当成它自己的子命令分隔符，因此必须用
    # -EncodedCommand(Base64) 把整段 PowerShell 命令打包成单个 token，
    # 避免内部的 ; 被 wt 拆开导致“找不到文件”。
    $escapedDir = $WorkingDirectory.Replace("'", "''")
    $fullCommand = "Set-Location -LiteralPath '$escapedDir'; `$Host.UI.RawUI.WindowTitle = '$Title'; $Command"
    $encoded = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($fullCommand))
    # 给含空格的 title 和目录套上字面引号：Start-Process 拼接数组时只用空格连接、
    # 不会自动加引号，否则 "RAG Ollama" 会被 wt 拆成 --title RAG + 程序名 Ollama。
    $wtArgs = @(
        "-w", $Script:WtWindowName,
        "new-tab",
        "--title", ('"{0}"' -f $Title),
        "-d", ('"{0}"' -f $WorkingDirectory),
        "powershell.exe", "-NoExit", "-ExecutionPolicy", "Bypass", "-EncodedCommand", $encoded
    )
    Start-Process -FilePath $WtPath -ArgumentList $wtArgs
    $Script:WtFirstTab = $false
}

# 根据 $Mode 把服务分发到独立窗口或 Windows Terminal 的 Tab。
function Start-Service([string]$Title, [string]$WorkingDirectory, [string]$Command) {
    if ($Script:UseTabs) {
        Start-ServiceTab $Script:WtPath $Title $WorkingDirectory $Command
    } else {
        Start-ServiceWindow $Title $WorkingDirectory $Command
    }
}

$Root = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $Root "backend"
$UserDir = Join-Path $Root "DjangoUserService"
$FrontDir = Join-Path $Root "front"

Write-Info "Project root: $Root"

if (-not (Test-Path $BackendDir)) { throw "backend directory not found: $BackendDir" }
if (-not (Test-Path $UserDir)) { throw "DjangoUserService directory not found: $UserDir" }
if (-not (Test-Path $FrontDir)) { throw "front directory not found: $FrontDir" }

# 解析启动模式：Terminal 需要 wt.exe，找不到则降级为 Window。
$Script:UseTabs = $false
$Script:WtPath = $null
if ($Mode -eq 'Terminal') {
    $Script:WtPath = Find-WindowsTerminal
    if ($Script:WtPath) {
        $Script:UseTabs = $true
        Write-Info "Startup mode: Terminal (single Windows Terminal window, multiple tabs)"
    } else {
        Write-Warn "Windows Terminal (wt.exe) not found. Falling back to separate windows."
        Write-Info "Startup mode: Window (separate PowerShell windows)"
    }
} else {
    Write-Info "Startup mode: Window (separate PowerShell windows)"
}

Write-Info "Checking infrastructure ports..."

if (Test-PortOpen "127.0.0.1" 3306) {
    Write-Ok "MySQL looks reachable on 127.0.0.1:3306"
} else {
    Write-Warn "MySQL is not reachable on 127.0.0.1:3306. Please start MySQL first, for example: net start mysql"
}

if (-not $SkipRedis) {
    if (Test-PortOpen "127.0.0.1" $RedisPort) {
        Write-Ok "Redis already running on 127.0.0.1:$RedisPort"
    } else {
        $redisServer = Find-CommandPath "redis-server"
        if ($redisServer) {
            Write-Info "Starting Redis on port $RedisPort..."
            Start-Service "RAG Redis" $Root "redis-server --port $RedisPort"
            Wait-PortOpen "Redis" "127.0.0.1" $RedisPort $WaitTimeoutSeconds | Out-Null
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
            Start-Service "RAG Ollama" $Root "ollama serve"
            Wait-PortOpen "Ollama" "127.0.0.1" 11434 $WaitTimeoutSeconds | Out-Null
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
        Start-Service "RAG Django User Service" $UserDir "uv run python manage.py runserver 127.0.0.1:$UserPort"
        # 后端鉴权依赖用户服务，必须等它就绪后再启动 FastAPI。
        Wait-PortOpen "Django user service" "127.0.0.1" $UserPort $WaitTimeoutSeconds | Out-Null
    }
}

if (-not $SkipBackend) {
    if (Test-PortOpen "127.0.0.1" $BackendPort) {
        Write-Ok "FastAPI backend already running on 127.0.0.1:$BackendPort"
    } else {
        $reloadFlag = if ($NoReload) { "" } else { " --reload" }
        Write-Info "Starting FastAPI backend..."
        Start-Service "RAG FastAPI Backend" $BackendDir "uv run uvicorn main:app --host 127.0.0.1 --port $BackendPort$reloadFlag"
        # 前端代理依赖后端，等后端端口就绪后再启动前端。
        Wait-PortOpen "FastAPI backend" "127.0.0.1" $BackendPort $WaitTimeoutSeconds | Out-Null
    }
}

if (-not $SkipFrontend) {
    if (Test-PortOpen "127.0.0.1" $FrontendPort) {
        Write-Ok "Frontend already running on 127.0.0.1:$FrontendPort"
    } else {
        $npm = Find-NpmCommand
        if (-not $npm) {
            Write-Warn "npm was not found. Install Node.js or add npm to PATH, then start frontend manually."
        } else {
            $npmDir = Split-Path -Parent $npm
            $frontendCommand = "`$env:Path = '$npmDir;' + `$env:Path; & '$npm' run dev -- --host 127.0.0.1 --port $FrontendPort"
            Write-Info "Starting React frontend..."
            Start-Service "RAG React Frontend" $FrontDir $frontendCommand
            Wait-PortOpen "Frontend" "127.0.0.1" $FrontendPort $WaitTimeoutSeconds | Out-Null
        }
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
Write-Host "  - Startup modes: -Mode Terminal (default, single Windows Terminal window with tabs) or -Mode Window (separate windows)."
Write-Host "  - For zero pop-up windows inside the editor, use VS Code: Terminal -> Run Task -> 'doki: start all'."
Write-Host "  - Keep the opened tabs/windows running."
Write-Host "  - Services start in stages (Redis/Ollama -> Django -> FastAPI -> Frontend); each waits for the previous to be ready."
Write-Host "  - Ports 18000/18001/18080 are chosen outside the Windows dynamic port range to avoid being reserved after reboot."
Write-Host "  - Restart this script after changing front/vite.config.ts."
Write-Host "  - Adjust readiness wait with -WaitTimeoutSeconds (default 90)."
Write-Host "  - If Redis/Ollama/MySQL are installed as services, starting them manually as services is also fine."
