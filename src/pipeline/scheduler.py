"""单 worker 串行调度器 — dequeue → process → mark done/failed → cleanup → sleep。

Spec ref: specs/task-queue-pipeline/spec.md + tasks.md §6
D-2: M1 不调 LLM
DouK 兜底: yt-dlp 失败重试 N 次后切 download_with_douk
correlation_id: 每条任务 UUID v4，贯穿全部日志
M3: LLM 总结 + 视觉理解集成（串行铁律: LLM → VLM）
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
from src.llm import get_summarizer, LLMError
from src.vision.heuristic_router import classify_video, RoutingDecision
from src.vision.keyframe_extractor import extract_keyframes
from src.vision.ocr_client import extract_text_from_image
from src.vision.vlm_client import describe_image
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

        # ── M3: LLM 总结（串行铁律: LLM 先执行）─────────────────────
        summary_result = None
        summary_error = None
        try:
            summarizer = get_summarizer(config)
            summary_result = summarizer.summarize(subtitle_vtt, metadata)
            _get_logger().info(
                "llm_summary_success",
                task_id=task_id,
                model=summary_result.model,
                key_points_count=len(summary_result.key_points),
                correlation_id=correlation_id,
            )
        except LLMError as e:
            summary_error = e.code
            _get_logger().warning(
                "llm_summary_failed",
                task_id=task_id,
                error_code=e.code,
                correlation_id=correlation_id,
            )
        except Exception as e:
            summary_error = str(e)
            _get_logger().warning(
                "llm_summary_error",
                task_id=task_id,
                error=str(e),
                correlation_id=correlation_id,
            )

        # ── M3: 视觉理解（串行铁律: LLM 完成后才开始）────────────────
        vlm_result = None
        ocr_texts = None
        vision_enabled = config.get("vision", {}).get("enabled", False)
        video_path = dl_result.get("video_path")
        video_duration = metadata.get("duration_seconds", 0)

        if vision_enabled and video_path and video_path.exists():
            # 启发式分流
            video_type = classify_video(subtitle_vtt, video_duration, 0)
            _get_logger().info(
                "vision_routing",
                task_id=task_id,
                video_type=video_type.value,
                correlation_id=correlation_id,
            )

            if video_type == RoutingDecision.SUMMARY_WITH_VLM:
                try:
                    # 抽取关键帧
                    keyframes_dir = tmp_dir / f"{video_id}_keyframes"
                    keyframes = extract_keyframes(video_path, keyframes_dir)

                    if keyframes:
                        # OCR 提取文字
                        ocr_texts = []
                        for kf in keyframes:
                            text = extract_text_from_image(kf)
                            if text:
                                ocr_texts.append(text)

                        # VLM 描述（逐帧推理）
                        vlm_descriptions = []
                        for kf in keyframes:
                            desc = describe_image(kf)
                            if desc:
                                vlm_descriptions.append(desc)

                        # 聚合 VLM 描述
                        vlm_result = "; ".join(vlm_descriptions) if vlm_descriptions else None

                        _get_logger().info(
                            "vision_processing_success",
                            task_id=task_id,
                            keyframe_count=len(keyframes),
                            ocr_text_count=len(ocr_texts),
                            vlm_description_count=len(vlm_descriptions),
                            correlation_id=correlation_id,
                        )
                except Exception as e:
                    _get_logger().warning(
                        "vision_processing_failed",
                        task_id=task_id,
                        error=str(e),
                        correlation_id=correlation_id,
                    )

        # ── 构建笔记 ──────────────────────────────────────────────────
        # 确定 processing_mode
        if vision_enabled and vlm_result:
            processing_mode = "subtitle_vlm"
        else:
            processing_mode = "subtitle_only"

        # 确定 summary_status
        if summary_result:
            summary_status = "done"
            summary_text = summary_result.summary_text
            ai_summary_model = summary_result.model
        else:
            summary_status = "failed"
            summary_text = ""
            ai_summary_model = None

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
            "pipeline_version": "m3",
            "status": "done",
            "downloader_used": dl_result.get("downloader_used", "yt-dlp"),
            "correlation_id": correlation_id,
            # M3 新增字段
            "summary_status": summary_status,
            "ai_summary_model": ai_summary_model,
            "processing_mode": processing_mode,
            "summary": summary_text,
        }
        fm = build_frontmatter(frontmatter_data)

        # 构建笔记正文
        note_body = build_note_body(
            subtitle_vtt=subtitle_vtt,
            metadata=metadata,
            local_cover_path="",
            correlation_id=correlation_id,
            raw_input=source_url,
            processing_time_seconds=0,
            summary_result=summary_result,
            summary_error=summary_error,
            vlm_result=vlm_result,
            ocr_texts=ocr_texts,
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

    # 4. 分片（mimo-asr 单次 10MB 限制，240秒/片 ≈ 7.5MB）
    try:
        from src.asr.audio_preprocess import split_audio_chunks
        chunks_dir = tmp_dir / f"{video_id}_chunks"
        chunks = split_audio_chunks(wav_path, chunks_dir)
    except Exception as e:
        _get_logger().error(
            "audio_split_failed",
            error=str(e),
            correlation_id=correlation_id,
        )
        return None

    # 5. ASR 转写（逐片转写 + 拼接）
    try:
        all_text_parts = []
        all_segments = []
        time_offset = 0.0

        for chunk_path in chunks:
            chunk_result = asr_client.transcribe(chunk_path)
            all_text_parts.append(chunk_result.text)
            # 为 segments 加上时间偏移
            for seg in chunk_result.segments:
                all_segments.append({
                    "start": seg.get("start", 0) + time_offset,
                    "end": seg.get("end", 0) + time_offset,
                    "text": seg.get("text", ""),
                })
            # 计算下一片的时间偏移
            if chunks.index(chunk_path) < len(chunks) - 1:
                from src.asr.audio_preprocess import get_audio_duration
                time_offset += get_audio_duration(chunk_path)

        full_text = " ".join(all_text_parts)
        subtitle_source = chunks[0] and "mimo_asr"  # 取第一片的 source
        _get_logger().info(
            "asr_transcribe_success",
            video_id=video_id,
            subtitle_source=subtitle_source,
            chunks=len(chunks),
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
        # 清理 .wav 和分片文件
        for chunk_path in chunks:
            if chunk_path.exists():
                try:
                    chunk_path.unlink()
                except OSError:
                    pass
        if chunks_dir.exists():
            try:
                chunks_dir.rmdir()
            except OSError:
                pass
        if wav_path.exists():
            try:
                wav_path.unlink()
            except OSError:
                pass

    # 6. 将转写结果写入临时 .vtt 文件供后续流程使用
    subtitle_path = tmp_dir / f"{video_id}.asr.vtt"
    # 格式化为简单 VTT（每段一行）
    vtt_lines = ["WEBVTT", ""]
    for seg in all_segments:
        start = seg.get("start", 0)
        end = seg.get("end", 0)
        text = seg.get("text", "")
        vtt_lines.append(f"{_format_time(start)} --> {_format_time(end)}")
        vtt_lines.append(text)
        vtt_lines.append("")
    subtitle_path.write_text("\n".join(vtt_lines), encoding="utf-8")
    dl_result["subtitle_path"] = subtitle_path
    dl_result["subtitle_source"] = "mimo_asr"

    return subtitle_source


def _format_time(seconds: float) -> str:
    """秒数格式化为 HH:MM:SS.mmm（VTT 时间戳格式）。"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


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
