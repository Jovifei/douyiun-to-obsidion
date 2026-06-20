# manual_e2e_test.ps1 — Manual E2E scenarios 1/2/6/7
# Plan ref: tasks.md §11.A
#
# Prerequisites:
#   1. FastAPI running:   python -m src.bridge.main  (port 8765)
#   2. Valid cookies.txt at config path
#   3. Real Douyin video URLs from Jovi
#
# Usage:
#   .\scripts\manual_e2e_test.ps1 -VideoUrl "https://www.douyin.com/video/XXXXX"

param(
    [Parameter(Mandatory=$false)]
    [string]$VideoUrl = "",

    [Parameter(Mandatory=$false)]
    [string]$NoSubtitleUrl = "",

    [Parameter(Mandatory=$false)]
    [string]$BaseUrl = "http://127.0.0.1:8765",

    [Parameter(Mandatory=$false)]
    [int]$VideoCount = 5,

    [Parameter(Mandatory=$false)]
    [int]$PollIntervalSec = 10,

    [Parameter(Mandatory=$false)]
    [int]$PollTimeoutSec = 180
)

$ErrorActionPreference = "Stop"

function Write-Result {
    param([string]$Scenario, [string]$Status, [string]$Detail)
    $icon = if ($Status -eq "PASS") { "[PASS]" } elseif ($Status -eq "FAIL") { "[FAIL]" } else { "[INFO]" }
    Write-Host "$icon $Scenario - $Detail" -ForegroundColor $(
        if ($Status -eq "PASS") { "Green" } elseif ($Status -eq "FAIL") { "Red" } else { "Cyan" }
    )
}

function Wait-TaskDone {
    param([int]$TaskId)
    $deadline = (Get-Date).AddSeconds($PollTimeoutSec)
    while ((Get-Date) -lt $deadline) {
        $resp = Invoke-RestMethod -Uri "$BaseUrl/tasks/$TaskId" -Method GET
        if ($resp.status -eq "done" -or $resp.status -eq "failed") {
            return $resp
        }
        Start-Sleep -Seconds $PollIntervalSec
    }
    return $null
}

Write-Host "=== M1 E2E Manual Test Script ===" -ForegroundColor Yellow
Write-Host "Base URL: $BaseUrl"
Write-Host ""

# -----------------------------------------------------------------------
# Scenario 1: Video WITH subtitles → done + note in vault
# -----------------------------------------------------------------------
Write-Host "--- Scenario 1: Video with subtitles ---" -ForegroundColor Cyan
if (-not $VideoUrl) {
    Write-Result "Scenario 1" "SKIP" "No -VideoUrl provided"
} else {
    try {
        $body = @{ source_url = $VideoUrl } | ConvertTo-Json
        $resp = Invoke-RestMethod -Uri "$BaseUrl/ingest" -Method POST -Body $body -ContentType "application/json"
        $taskId = $resp.task_id
        Write-Result "Scenario 1a" "INFO" "Enqueued task_id=$taskId, status=$($resp.status)"

        $result = Wait-TaskDone -TaskId $taskId
        if ($null -eq $result) {
            Write-Result "Scenario 1" "FAIL" "Timeout: task $taskId did not complete in ${PollTimeoutSec}s"
        } elseif ($result.status -eq "done") {
            Write-Result "Scenario 1b" "PASS" "Task $taskId completed: note_path=$($result.note_path)"
        } else {
            Write-Result "Scenario 1" "FAIL" "Task $taskId ended with status=$($result.status), error=$($result.error_code)"
        }
    } catch {
        Write-Result "Scenario 1" "FAIL" "Exception: $_"
    }
}

# -----------------------------------------------------------------------
# Scenario 2: Video WITHOUT subtitles → failed + error_code
# -----------------------------------------------------------------------
Write-Host ""
Write-Host "--- Scenario 2: Video without subtitles ---" -ForegroundColor Cyan
if (-not $NoSubtitleUrl) {
    Write-Result "Scenario 2" "SKIP" "No -NoSubtitleUrl provided"
} else {
    try {
        $body = @{ source_url = $NoSubtitleUrl } | ConvertTo-Json
        $resp = Invoke-RestMethod -Uri "$BaseUrl/ingest" -Method POST -Body $body -ContentType "application/json"
        $taskId = $resp.task_id
        Write-Result "Scenario 2a" "INFO" "Enqueued task_id=$taskId"

        $result = Wait-TaskDone -TaskId $taskId
        if ($null -eq $result) {
            Write-Result "Scenario 2" "FAIL" "Timeout: task $taskId did not complete"
        } elseif ($result.status -eq "failed" -and $result.error_code -eq "no_subtitle_in_m1") {
            Write-Result "Scenario 2" "PASS" "Task $taskId failed as expected: error_code=$($result.error_code)"
        } else {
            Write-Result "Scenario 2" "FAIL" "Expected failed+no_subtitle_in_m1, got status=$($result.status) error=$($result.error_code)"
        }
    } catch {
        Write-Result "Scenario 2" "FAIL" "Exception: $_"
    }
}

# -----------------------------------------------------------------------
# Scenario 6: Network disconnect 30s then resume
# -----------------------------------------------------------------------
Write-Host ""
Write-Host "--- Scenario 6: Network disconnect simulation ---" -ForegroundColor Cyan
Write-Result "Scenario 6" "SKIP" "Requires manual network disconnect - see E2E_TEST_GUIDE.md"
Write-Host "  Steps:"
Write-Host "  1. Disable network adapter or pull cable"
Write-Host "  2. Wait 30 seconds"
Write-Host "  3. Re-enable network"
Write-Host "  4. curl POST /ingest with a valid URL"
Write-Host "  5. Verify task enters queue and eventually completes"

# -----------------------------------------------------------------------
# Scenario 7: Performance benchmark — 5 videos serial
# -----------------------------------------------------------------------
Write-Host ""
Write-Host "--- Scenario 7: Performance benchmark ($VideoCount videos) ---" -ForegroundColor Cyan
if (-not $VideoUrl) {
    Write-Result "Scenario 7" "SKIP" "No -VideoUrl provided"
} else {
    $durations = @()
    for ($i = 1; $i -le $VideoCount; $i++) {
        Write-Host "  [$i/$VideoCount] Ingesting..."
        $start = Get-Date
        try {
            $body = @{ source_url = $VideoUrl; force = $true } | ConvertTo-Json
            $resp = Invoke-RestMethod -Uri "$BaseUrl/ingest" -Method POST -Body $body -ContentType "application/json"
            $taskId = $resp.task_id

            $result = Wait-TaskDone -TaskId $taskId
            $elapsed = ((Get-Date) - $start).TotalSeconds
            $durations += $elapsed

            if ($result.status -eq "done") {
                Write-Result "Scenario 7[$i]" "PASS" "Completed in $([math]::Round($elapsed, 1))s"
            } else {
                Write-Result "Scenario 7[$i]" "FAIL" "Status=$($result.status) in $([math]::Round($elapsed, 1))s"
            }
        } catch {
            $elapsed = ((Get-Date) - $start).TotalSeconds
            $durations += $elapsed
            Write-Result "Scenario 7[$i]" "FAIL" "Exception in $([math]::Round($elapsed, 1))s: $_"
        }
    }

    if ($durations.Count -gt 0) {
        $avg = ($durations | Measure-Object -Average).Average
        Write-Host ""
        Write-Result "Scenario 7" $(if ($avg -le 120) { "PASS" } else { "FAIL" }) `
            "Average: $([math]::Round($avg, 1))s per video (target: <= 120s)"
    }
}

Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Yellow
