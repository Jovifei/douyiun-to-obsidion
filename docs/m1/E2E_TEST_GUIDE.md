# M1 E2E Test Guide

Plan ref: tasks.md §11.A

## Overview

7 end-to-end scenarios testing the full pipeline: curl -> FastAPI -> pipeline -> vault.

- **Scenarios 3/4/5**: Automated (pytest, no network)
- **Scenarios 1/2/6/7**: Manual (requires real Douyin URLs + running server)

## Prerequisites

1. **FastAPI server running** on `127.0.0.1:8765`:
   ```
   python -m src.bridge.main
   ```

2. **Valid cookies.txt** at the path configured in `config.yaml`

3. **Real Douyin video URLs** from Jovi:
   - One video WITH native subtitles (for scenario 1)
   - One video WITHOUT subtitles (for scenario 2)

## Running Automated Tests

```bash
# Run all automated E2E scenarios (3, 4, 5)
pytest tests/e2e/test_curl_e2e.py -v

# Run specific scenario
pytest tests/e2e/test_curl_e2e.py::TestScenario3DuplicateDetection -v
pytest tests/e2e/test_curl_e2e.py::TestScenario4ZombieReclaim -v
pytest tests/e2e/test_curl_e2e_test_curl_e2e.py::TestScenario5CookieExpired -v
```

### What the automated tests cover

| Scenario | Test | What it verifies |
|----------|------|------------------|
| 3 | `test_second_ingest_returns_already_archived` | Same URL ingested twice -> second returns `already_archived: true` |
| 3 | `test_force_overrides_duplicate` | `force=true` bypasses duplicate detection |
| 4 | `test_zombie_reclaim_on_startup` | Stale `fetching` task is reclaimed to `pending` |
| 4 | `test_zombie_reclaim_via_api_startup_hook` | Startup hook triggers reclaim |
| 4 | `test_fresh_task_not_reclaimed` | Recently claimed tasks are not reclaimed |
| 5 | `test_cookie_expired_error_code` | Cookie error produces `error_code=cookie_expired` |
| 5 | `test_cookie_expired_via_api_task_status` | `GET /tasks/{id}` returns the error_code |

## Running Manual Tests

### PowerShell script

```powershell
# Basic usage (skip scenarios needing URLs)
.\scripts\manual_e2e_test.ps1

# With video URLs
.\scripts\manual_e2e_test.ps1 `
    -VideoUrl "https://www.douyin.com/video/XXXXX" `
    -NoSubtitleUrl "https://www.douyin.com/video/YYYYY"

# Performance benchmark (5 videos)
.\scripts\manual_e2e_test.ps1 `
    -VideoUrl "https://www.douyin.com/video/XXXXX" `
    -VideoCount 5 `
    -PollTimeoutSec 300
```

### Manual scenario steps

#### Scenario 1: Video with subtitles

```bash
# 1. Ingest
curl -X POST http://127.0.0.1:8765/ingest \
  -H "Content-Type: application/json" \
  -d '{"source_url": "VIDEO_URL_WITH_SUBTITLES"}'

# 2. Note the task_id from response, poll until done
curl http://127.0.0.1:8765/tasks/TASK_ID

# 3. Verify: status="done", note_path points to .md in vault
```

Expected: Note appears in vault under `inbox/douyin/YYYY-MM/VIDEO_ID.md` within 2 minutes.

#### Scenario 2: Video without subtitles

```bash
# Same as above but with a video lacking subtitles
# Expected: status="failed", error_code="no_subtitle_in_m1" within 30 seconds
```

#### Scenario 6: Network disconnect

1. Start an ingest for a video with subtitles
2. Disable network adapter / pull cable
3. Wait 30 seconds
4. Re-enable network
5. Verify: the task either completes (if download was already done) or fails with a recoverable error
6. Submit a new ingest -> verify it enters queue and processes normally

#### Scenario 7: Performance benchmark

```bash
# Ingest 5 videos serially, measure average time
.\scripts\manual_e2e_test.ps1 -VideoUrl "VIDEO_URL" -VideoCount 5
```

Target: average end-to-end <= 120 seconds per video.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Server not responding | Check `config.yaml` host/port, ensure `python -m src.bridge.main` is running |
| Cookie expired errors | Update `cookies.txt` with fresh cookies from browser |
| Task stuck in `fetching` | Check scheduler logs; zombie reclaim runs at startup (30min timeout) |
| No note in vault | Check `vault` path in config, verify `inbox/douyin/` directory exists |
