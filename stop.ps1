# =====================================================================
# PROJECT WROCK: SERVICE SHUTDOWN UTILITY
# =====================================================================

Write-Host "Stopping Project Wrock services..." -ForegroundColor Yellow

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

function Stop-DockProcess {
    try {
        Get-CimInstance Win32_Process -Filter "CommandLine LIKE '%floating_dock.py%'" -ErrorAction SilentlyContinue | ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    } catch {}
}

Stop-PortProcess 8000
Stop-PortProcess 3000
Stop-DockProcess

Write-Host "Project Wrock services stopped cleanly." -ForegroundColor Green
