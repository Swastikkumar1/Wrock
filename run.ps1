# =====================================================================
# PROJECT WROCK: NON-BLOCKING SPATIAL-AI & OS AUTOMATION LAUNCHER
# User: Swastik
# =====================================================================

Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host "         PROJECT WROCK - SPATIAL-AI CORE LAUNCHER         " -ForegroundColor Yellow
Write-Host "===========================================================" -ForegroundColor Cyan

$CurrentDir = $PSScriptRoot
if (-not $CurrentDir) { $CurrentDir = Get-Location }

# Function to safely free any lingering processes on ports
function Stop-PortProcess ($Port) {
    try {
        $conns = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
        if ($conns) {
            foreach ($c in $conns) {
                if ($c.OwningProcess -and $c.OwningProcess -gt 0) {
                    Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
                }
            }
        }
    } catch {}
}

# Function to actively poll until port is verified accepting TCP connections
function Test-PortReady ($Port, $TimeoutSeconds = 25) {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        try {
            $tcp = New-Object System.Net.Sockets.TcpClient
            $connect = $tcp.BeginConnect("127.0.0.1", $Port, $null, $null)
            $wait = $connect.AsyncWaitHandle.WaitOne(400, $false)
            if ($wait -and $tcp.Connected) {
                $tcp.EndConnect($connect)
                $tcp.Close()
                return $true
            }
            $tcp.Close()
        } catch {}
        Start-Sleep -Milliseconds 250
    }
    return $false
}

# 1. Clean previous stale processes
Write-Host "[1/4] Ensuring clean ports (8000 & 3000)..." -ForegroundColor White
Stop-PortProcess 8000
Stop-PortProcess 3000

# 2. Fast Dependency Check: only run install if node_modules is missing
$hudNodeModules = Join-Path $CurrentDir "interface\hud\node_modules"
if (-not (Test-Path $hudNodeModules)) {
    Write-Host "Installing HUD frontend dependencies (one-time setup)..." -ForegroundColor Yellow
    Start-Process powershell -Wait -ArgumentList "-Command", "cd '$CurrentDir\interface\hud'; npm install"
}

# Ensure logs directory exists
$LogDir = Join-Path $CurrentDir "logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
$BackendLog = Join-Path $LogDir "backend.log"
$HudLog = Join-Path $LogDir "hud.log"

# 3. Start Backend in background (Hidden - no ugly popup console windows)
Write-Host "[2/4] Starting FastAPI & AI Intelligence Core..." -ForegroundColor Green
Start-Process powershell -WindowStyle Hidden -ArgumentList "-Command", "cd '$CurrentDir'; python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 *> '$BackendLog'"

# 4. Start Interface HUD Vite Server in background (Hidden - no ugly popup console windows)
Write-Host "[3/4] Starting Holographic Arc-Reactor HUD Server..." -ForegroundColor Green
$HudDir = Join-Path $CurrentDir "interface\hud"
Start-Process powershell -WindowStyle Hidden -ArgumentList "-Command", "cd '$HudDir'; npm run dev *> '$HudLog'"

# 5. Wait for servers to be 100% verified online before launching browser
Write-Host "Verifying backend online (Port 8000)..." -NoNewline -ForegroundColor White
$backendReady = Test-PortReady 8000 20
if ($backendReady) {
    Write-Host " [ONLINE]" -ForegroundColor Green
} else {
    Write-Host " [INITIALIZING]" -ForegroundColor Yellow
}

Write-Host "Verifying HUD interface ready (Port 3000)..." -NoNewline -ForegroundColor White
$hudReady = Test-PortReady 3000 20
if ($hudReady) {
    Write-Host " [ONLINE]" -ForegroundColor Green
} else {
    Write-Host " [INITIALIZING]" -ForegroundColor Yellow
}

# 6. Launch browser window in sleek app mode
Write-Host "[4/4] Opening Holographic HUD Window..." -ForegroundColor Cyan

$chromePath = (Get-ItemProperty "HKLM:\Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe" -ErrorAction SilentlyContinue).'(Default)'
$edgePath = (Get-ItemProperty "HKLM:\Software\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe" -ErrorAction SilentlyContinue).'(Default)'

if ($chromePath -and (Test-Path $chromePath)) {
    Start-Process $chromePath -ArgumentList "--app=http://localhost:3000", "--window-size=1280,840"
} elseif ($edgePath -and (Test-Path $edgePath)) {
    Start-Process $edgePath -ArgumentList "--app=http://localhost:3000", "--window-size=1280,840"
} else {
    Start-Process "http://localhost:3000"
}

Write-Host "`n===========================================================" -ForegroundColor Cyan
Write-Host "             WROCK IS ONLINE & READY, SWASTIK!            " -ForegroundColor Green
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host "  -> Holographic Interface: http://localhost:3000" -ForegroundColor White
Write-Host "  -> Backend Intelligence:  http://localhost:8000" -ForegroundColor White
Write-Host "  -> Say 'Wake up Wrock' ONCE to initiate." -ForegroundColor Yellow
Write-Host "  -> Press Ctrl+C in this window to stop Wrock services." -ForegroundColor White
Write-Host "  -> (Or run .\stop.ps1 from another terminal anytime)." -ForegroundColor Gray
Write-Host "===========================================================`n" -ForegroundColor Cyan

try {
    while ($true) {
        Start-Sleep -Seconds 1
    }
} finally {
    Write-Host "`nShutting down Project Wrock services..." -ForegroundColor Yellow
    Stop-PortProcess 8000
    Stop-PortProcess 3000
    Write-Host "All Wrock services stopped cleanly.`n" -ForegroundColor Green
}
