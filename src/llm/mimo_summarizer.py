"""MimoSummarizer — M3 Task 2 + M6 Task 1。

通过 mimo-v2.5-pro API 生成 3-5 要点总结。
M6: 改用 OpenAICompatibleLLM 统一客户端。
"""
import json
import re

from src.llm import LLMError, SummarizerClient, SummaryResult
from src.llm.client import OpenAICompatibleLLM

# ── 截断阈值 ────────────────────────────────────────────────────────

_MAX_TEXT_LEN = 8000
_HALF = 4000

# ── prompt 模板 (D-M3-4，优化版) ──────────────────────────────────────

_PROMPT_SYSTEM = """\
你是一名知识管理助手，专门从视频字幕中提炼可执行知识。
输出必须是严格 JSON，不含任何额外文本或 markdown。
"""

_PROMPT_TEMPLATE = """\
请根据以下视频字幕生成结构化笔记。

视频标题：{title}
视频作者：{author}
视频时长：{duration}秒

## 要求
1. 提炼 **3-5 个核心要点**（按重要性排序）
2. 每个要点必须是**可执行的知识**（不是泛泛而谈的总结）
3. 每个要点限 30 字以内，一句话概括
4. 如果字幕内容是教程类，要点必须是"操作步骤"而非"讲解内容"
5. 如果字幕内容是观点类，要点必须是"核心论点"而非"论据细节"
6. 使用中文

## 字幕文本
{subtitle_text}

## 输出格式（严格 JSON）
```json
{{"key_points": ["要点1", "要点2", "要点3"]}}
```"""


# ── MimoSummarizer ──────────────────────────────────────────────────


class MimoSummarizer(SummarizerClient):
    """MiMo LLM 总结客户端 — 通过 OpenAICompatibleLLM 调 mimo-v2.5-pro API。"""

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://token-plan-cn.xiaomimimo.com/v1",
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client = OpenAICompatibleLLM(
            base_url=self.base_url,
            api_key=self.api_key,
            default_model="mimo-v2.5-pro",
        )

    def summarize(self, subtitle_text: str, metadata: dict) -> SummaryResult:
        """总结字幕文本并返回 SummaryResult。

        Args:
            subtitle_text: 字幕文本。
            metadata: 视频元数据（标题、作者等）。

        Returns:
            SummaryResult 实例。

        Raises:
            LLMError: API 调用超时或返回空结果。
        """
        # 截断逻辑
        text = self._truncate(subtitle_text)

        # 构造 prompt（带视频元数据上下文）
        prompt = _PROMPT_TEMPLATE.format(
            title=metadata.get("title", "未知标题"),
            author=metadata.get("uploader", "未知作者"),
            duration=int(metadata.get("duration_seconds", 0)),
            subtitle_text=text,
        )

        # 调 mimo-v2.5-pro API（通过 OpenAICompatibleLLM）
        messages = [
            {"role": "system", "content": _PROMPT_SYSTEM},
            {"role": "user", "content": prompt},
        ]

        try:
            from src.llm.client import LLMClientError

            content = self._client.chat(messages)
        except LLMClientError as e:
            if "超时" in e.message:
                raise LLMError("llm_timeout")
            raise LLMError("llm_network_error", str(e))

        if not content or not content.strip():
            raise LLMError("empty_summary")

        # 解析 key_points
        key_points = self._parse_key_points(content)

        return SummaryResult(
            summary_text=content.strip(),
            key_points=key_points,
            model="mimo-v2.5-pro",
            source="mimo_llm",
        )

    @staticmethod
    def _truncate(text: str) -> str:
        """截断超过 8000 字的文本，保留前后各 4000 字。"""
        if len(text) <= _MAX_TEXT_LEN:
            return text
        return text[:_HALF] + "\n...\n" + text[-_HALF:]

    @staticmethod
    def _parse_key_points(content: str) -> list[str]:
        """从 API 响应中解析 key_points 列表。

        支持两种格式：
        1. JSON: {"key_points": ["p1", "p2"]}
        2. 文本列表: - 要点1\\n- 要点2
        """
        # 尝试 JSON 解析
        try:
            # 处理 ```json ... ``` 包裹
            json_str = content
            if "```json" in content:
                json_str = content.split("```json", 1)[1].split("```", 1)[0].strip()
            elif "```" in content:
                json_str = content.split("```", 1)[1].split("```", 1)[0].strip()

            # 找到第一个 { 和最后一个 }
            start = json_str.find("{")
            end = json_str.rfind("}")
            if start != -1 and end > start:
                parsed = json.loads(json_str[start : end + 1])
                if isinstance(parsed, dict) and "key_points" in parsed:
                    points = parsed["key_points"]
                    if isinstance(points, list) and 3 <= len(points) <= 5:
                        return [str(p) for p in points]
                    if isinstance(points, list):
                        return [str(p) for p in points[:5]]
        except (json.JSONDecodeError, ValueError):
            pass

        # 降级：从文本中提取 - 开头的行
        points = []
        for line in content.splitlines():
            line = line.strip()
            if re.match(r"^[-•]\s+", line):
                point = re.sub(r"^[-•]\s+", "", line).strip()
                if point:
                    points.append(point)
        if points:
            return points[:5]

        # 最终降级：按句号分割
        sentences = [s.strip() for s in re.split(r"[。！？]", content) if s.strip()]
        return sentences[:5]
