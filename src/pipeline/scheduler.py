"""单 worker 串行调度器 — dequeue → process → mark done/failed → cleanup → sleep。

Spec ref: specs/task-queue-pipeline/spec.md + tasks.md §6
D-2: M1 不调 LLM
DouK 兜底: yt-dlp 失败重试 N 次后切 download_with_douk
correlation_id: 每条任务 UUID v4，贯穿全部日志
"""
import time
from datetime import datetime, timezone
from pathlib import Path

import structlog

from src.extractors import (
    resolve_url,
    download_video,
    download_video_only,
    extract_metadata,
    download_with_douk,
    NoSubtitleError,
)
from src.asr import get_asr_client, ASRError
from src.asr.audio_preprocess import extract_audio_for_asr
from src.obsidian.frontmatter import build_frontmatter
from src.obsidian.note_builder import build_note_body
from src.obsidian.writer import write_note
from src.queue import db
from src.pipeline.state_machine import transition
from src.pipeline.errors import classify_exception
from src.utils.cookie_probe import probe_cookie
from src.utils.logging_config import configure_logging

# structlog 配置移到 configure_logging() 函数中（Task 11 reviewer 指出）
# logger 延迟获取：configure_logging() 先跑再用 logger，否则 filter_by_level 报 NoneType
def _get_logger():
    return structlog.get_logger(__name__)


def process_task(conn, task: dict, config: dict) -> None:
    """处理单条任务：fetching → writing → done。

    失败时 catching 异常并置 failed。
    """
    task_id = task["id"]
    video_id = task["video_id"]
    source_url = task["source_url"]
    correlation_id = task.get("correlation_id", "")

    _get_logger().info(
        "task_processing_start",
        task_id=task_id,
        correlation_id=correlation_id,
    )

    tmp_dir = Path(config.get("downloader", {}).get("temp_dir", "/tmp/douyin"))
    tmp_dir.mkdir(parents=True, exist_ok=True)

    try:
        # ── fetching 阶段 ──────────────────────────────────────────────
        resolved = resolve_url(source_url)
        canonical_url = resolved["canonical_url"]
        _get_logger().info(
            "url_resolved",
            task_id=task_id,
            canonical_url=canonical_url,
            source_url_type=resolved["source_url_type"],
            correlation_id=correlation_id,
        )

        # 下载（含 yt-dlp 重试 + DouK 兜底）
        dl_result = _download_with_fallback(
            video_id, canonical_url, tmp_dir, config, correlation_id
        )

        subtitle_source = dl_result["subtitle_source"]
        if subtitle_source is None or subtitle_source == "none":
            # M2: 无字幕时走 ASR 路径
            subtitle_source = _run_asr_fallback(
                dl_result, video_id, tmp_dir, config, correlation_id
            )
            if subtitle_source is None:
                # ASR 也失败，置 failed
                transition(
                    conn, task_id, "failed",
                    from_status="fetching",
                    correlation_id=correlation_id,
                    error_code="asr_failed",
                    error_message="ASR transcription failed",
                )
                return

        info_dict = dl_result.get("info_dict") or {}
        metadata = extract_metadata(info_dict)

        # ── writing 阶段 ───────────────────────────────────────────────
        transition(
            conn, task_id, "writing",
            from_status="fetching",
            correlation_id=correlation_id,
        )

        vault_root = Path(config.get("vault", {}).get("root", ""))

        # 读取字幕内容
        subtitle_vtt = ""
        if dl_result.get("subtitle_path") and dl_result["subtitle_path"].exists():
            subtitle_vtt = dl_result["subtitle_path"].read_text(encoding="utf-8")

        # 构建 frontmatter
        frontmatter_data = {
            "title": metadata.get("title", ""),
            "video_id": video_id,
            "source_url": source_url,
            "source_url_type": task.get("source_url_type", ""),
            "author": metadata.get("uploader", ""),
            "uploader_id": metadata.get("uploader_id", ""),
            "duration_seconds": metadata.get("duration_seconds", 0),
            "uploaded_at": metadata.get("uploaded_at", ""),
            "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "cover_url": metadata.get("thumbnail", ""),
            "local_cover_path": "",
            "subtitle_source": subtitle_source,
            "subtitle_language": "zh",
            "pipeline_version": "m1",
            "status": "done",
            "downloader_used": dl_result.get("downloader_used", "yt-dlp"),
            "correlation_id": correlation_id,
        }
        fm = build_frontmatter(frontmatter_data)

        note_body = build_note_body(
            subtitle_vtt=subtitle_vtt,
            metadata=metadata,
            local_cover_path="",
            correlation_id=correlation_id,
            raw_input=source_url,
            processing_time_seconds=0,
        )

        write_note(
            vault_root=vault_root,
            video_id=video_id,
            frontmatter_dict=fm,
            note_body=note_body,
            cover_url=metadata.get("thumbnail", ""),
            capture_time=datetime.now(timezone.utc),
        )

        # ── 清理临时文件 ───────────────────────────────────────────────
        _cleanup_tmp_files(dl_result, tmp_dir, video_id)

        # ── done ───────────────────────────────────────────────────────
        transition(
            conn, task_id, "done",
            from_status="writing",
            correlation_id=correlation_id,
        )
        _get_logger().info(
            "task_processing_done",
            task_id=task_id,
            correlation_id=correlation_id,
        )

    except NoSubtitleError:
        # M2: 无字幕时走 ASR 路径（而非直接 failed）
        try:
            # 构造一个空的 dl_result 供 ASR 使用
            empty_dl_result = {
                "video_path": None,
                "subtitle_path": None,
                "subtitle_source": None,
                "downloader_used": "yt-dlp",
                "info_dict": {},
                "title": None,
                "duration": None,
                "uploader": None,
                "uploader_url": None,
                "thumbnail": None,
                "canonical_url": source_url,
            }
            subtitle_source = _run_asr_fallback(
                empty_dl_result, video_id, tmp_dir, config, correlation_id
            )
            if subtitle_source is None:
                transition(
                    conn, task_id, "failed",
                    from_status="fetching",
                    correlation_id=correlation_id,
                    error_code="asr_failed",
                    error_message="ASR transcription failed",
                )
                return

            # ASR 成功，继续 writing 阶段
            info_dict = empty_dl_result.get("info_dict") or {}
            metadata = extract_metadata(info_dict)

            transition(
                conn, task_id, "writing",
                from_status="fetching",
                correlation_id=correlation_id,
            )

            vault_root = Path(config.get("vault", {}).get("root", ""))

            subtitle_vtt = ""
            if empty_dl_result.get("subtitle_path") and empty_dl_result["subtitle_path"].exists():
                subtitle_vtt = empty_dl_result["subtitle_path"].read_text(encoding="utf-8")

            frontmatter_data = {
                "title": metadata.get("title", ""),
                "video_id": video_id,
                "source_url": source_url,
                "source_url_type": task.get("source_url_type", ""),
                "author": metadata.get("uploader", ""),
                "uploader_id": metadata.get("uploader_id", ""),
                "duration_seconds": metadata.get("duration_seconds", 0),
                "uploaded_at": metadata.get("uploaded_at", ""),
                "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "cover_url": metadata.get("thumbnail", ""),
                "local_cover_path": "",
                "subtitle_source": subtitle_source,
                "subtitle_language": "zh",
                "pipeline_version": "m2",
                "status": "done",
                "downloader_used": empty_dl_result.get("downloader_used", "yt-dlp"),
                "correlation_id": correlation_id,
            }
            fm = build_frontmatter(frontmatter_data)

            note_body = build_note_body(
                subtitle_vtt=subtitle_vtt,
                metadata=metadata,
                local_cover_path="",
                correlation_id=correlation_id,
                raw_input=source_url,
                processing_time_seconds=0,
            )

            write_note(
                vault_root=vault_root,
                video_id=video_id,
                frontmatter_dict=fm,
                note_body=note_body,
                cover_url=metadata.get("thumbnail", ""),
                capture_time=datetime.now(timezone.utc),
            )

            _cleanup_tmp_files(empty_dl_result, tmp_dir, video_id)

            transition(
                conn, task_id, "done",
                from_status="writing",
                correlation_id=correlation_id,
            )
            _get_logger().info(
                "task_processing_done_asr",
                task_id=task_id,
                correlation_id=correlation_id,
            )

        except Exception as asr_e:
            _handle_task_failure(conn, task_id, correlation_id, asr_e)

    except Exception as e:
        _handle_task_failure(conn, task_id, correlation_id, e)


def _download_with_fallback(
    video_id: str,
    canonical_url: str,
    tmp_dir: Path,
    config: dict,
    correlation_id: str,
) -> dict:
    """yt-dlp 重试 N 次后切 DouK 兜底。返回下载结果 dict。"""
    max_retries = config.get("downloader", {}).get("yt_dlp_retries", 3)
    douk_path = config.get("downloader", {}).get("douk_path", "")

    # yt-dlp 重试
    last_error = None
    for attempt in range(max_retries):
        try:
            result = download_video(
                video_id=video_id,
                canonical_url=canonical_url,
                out_dir=tmp_dir,
                cookies_path=config.get("downloader", {}).get("cookies_path") or None,
            )
            return result
        except Exception as e:
            last_error = e
            _get_logger().warning(
                "ytdlp_attempt_failed",
                attempt=attempt + 1,
                max_retries=max_retries,
                error=str(e),
                correlation_id=correlation_id,
            )

    # DouK 兜底
    if douk_path:
        _get_logger().info(
            "douk_fallback_triggered",
            correlation_id=correlation_id,
        )
        try:
            result = download_with_douk(
                video_id=video_id,
                canonical_url=canonical_url,
                out_dir=tmp_dir,
                douk_path=douk_path,
            )
            return result
        except Exception as e:
            _get_logger().error(
                "douk_fallback_failed",
                error=str(e),
                correlation_id=correlation_id,
            )
            raise

    # 所有工具都失败
    raise last_error


def _run_asr_fallback(
    dl_result: dict,
    video_id: str,
    tmp_dir: Path,
    config: dict,
    correlation_id: str,
) -> str | None:
    """无字幕时走 ASR 路径：下载视频 → 提取音频 → 转写。

    Returns:
        subtitle_source 字符串，失败返回 None。

    Raises:
        ASRError: ASR 转写失败。
    """
    _get_logger().info(
        "asr_fallback_triggered",
        video_id=video_id,
        correlation_id=correlation_id,
    )

    # 1. 获取 ASR client
    try:
        asr_client = get_asr_client(config)
    except ValueError as e:
        _get_logger().error(
            "asr_client_init_failed",
            error=str(e),
            correlation_id=correlation_id,
        )
        return None

    # 2. 如果没有视频文件，需要重新下载
    video_path = dl_result.get("video_path")
    if video_path is None or not video_path.exists():
        _get_logger().info(
            "asr_redownloading_video_only",
            video_id=video_id,
            correlation_id=correlation_id,
        )
        cookies_path = config.get("downloader", {}).get("cookies_path") or None
        dl_only_result = download_video_only(
            url=dl_result.get("canonical_url", ""),
            out_dir=tmp_dir,
            cookies_path=cookies_path,
        )
        video_path = dl_only_result["video_path"]

    # 3. 提取音频
    wav_path = tmp_dir / f"{video_id}.wav"
    try:
        extract_audio_for_asr(video_path, wav_path)
    except Exception as e:
        _get_logger().error(
            "audio_extract_failed",
            error=str(e),
            correlation_id=correlation_id,
        )
        return None

    # 4. ASR 转写
    try:
        result = asr_client.transcribe(wav_path)
        subtitle_source = result.source or "asr"
        _get_logger().info(
            "asr_transcribe_success",
            video_id=video_id,
            subtitle_source=subtitle_source,
            correlation_id=correlation_id,
        )
    except ASRError as e:
        _get_logger().error(
            "asr_transcribe_failed",
            error=str(e),
            correlation_id=correlation_id,
        )
        raise
    finally:
        # 清理 .wav 文件
        if wav_path.exists():
            try:
                wav_path.unlink()
            except OSError:
                pass

    # 5. 将转写结果写入临时 .vtt 文件供后续流程使用
    subtitle_path = tmp_dir / f"{video_id}.asr.vtt"
    subtitle_path.write_text(result.text, encoding="utf-8")
    dl_result["subtitle_path"] = subtitle_path
    dl_result["subtitle_source"] = subtitle_source

    return subtitle_source


def _handle_task_failure(conn, task_id: int, correlation_id: str, error: Exception) -> None:
    """将异常映射为 error_code 并置任务为 failed。"""
    error_str = str(error)
    # 使用 classify_exception 替代内联字符串匹配
    error_code = classify_exception(error).value

    _get_logger().error(
        "task_processing_failed",
        task_id=task_id,
        error_code=error_code,
        error=error_str,
        correlation_id=correlation_id,
    )
    transition(
        conn, task_id, "failed",
        from_status=None,  # will read from DB
        correlation_id=correlation_id,
        error_code=error_code,
        error_message=error_str[:500],
    )


def _cleanup_tmp_files(dl_result: dict, tmp_dir: Path, video_id: str) -> None:
    """清理临时 .mp4 / .vtt / .wav 文件。"""
    for suffix in (".mp4", ".webm", ".zh.vtt", ".zh.srt", ".wav", ".asr.vtt"):
        p = tmp_dir / f"{video_id}{suffix}"
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass


def run_once(db_path, config: dict) -> None:
    """处理一条任务（供测试用，不无限循环）。"""
    # 配置日志（函数式 API）
    configure_logging(config, module_name="scheduler")

    conn = db.init_db(db_path)
    try:
        task = db.atomic_dequeue(conn)
        if task is None:
            return
        process_task(conn, task, config)
    finally:
        conn.close()


def run_forever(db_path, config: dict) -> None:
    """主循环：dequeue → process_task → mark done/failed → cleanup → sleep 5s → 循环。"""
    # 配置日志（函数式 API，替代模块顶层 structlog.configure）
    configure_logging(config, module_name="scheduler")

    conn = db.init_db(db_path)
    _get_logger().info("scheduler_started", db_path=str(db_path))

    # cookie 探活（启动时用 HTTP 探活，不只是文件存在检查）
    cookies_path = config.get("downloader", {}).get("cookies_path", "")
    if cookies_path:
        test_url = config.get("cookie_test_url", "https://v.douyin.com/test/")
        probe_ok = probe_cookie(cookies_path, test_url)
        _get_logger().info("cookies_probe_result", path=cookies_path, ok=probe_ok)

    # 复活 zombie 任务
    zombie_count = db.reclaim_zombie_tasks(conn, timeout_minutes=config.get("queue", {}).get("zombie_timeout_minutes", 30))
    if zombie_count > 0:
        _get_logger().info("zombies_reclaimed", count=zombie_count)

    try:
        while True:
            task = db.atomic_dequeue(conn)
            if task is None:
                time.sleep(5)
                continue
            process_task(conn, task, config)
    except KeyboardInterrupt:
        _get_logger().info("scheduler_stopped")
    finally:
        conn.close()
