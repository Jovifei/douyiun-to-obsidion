"""MimoSummarizer — M3 Task 2。

通过 mimo-v2.5-pro API 生成 3-5 要点总结。
API 格式：chat/completions + messages。
"""
import json
import re

import httpx

from src.llm import LLMError, SummarizerClient, SummaryResult

# ── 截断阈值 ────────────────────────────────────────────────────────

_MAX_TEXT_LEN = 8000
_HALF = 4000

# ── prompt 模板 (D-M3-4) ────────────────────────────────────────────

_PROMPT_TEMPLATE = """\
请根据以下视频字幕文本生成结构化总结。

要求：
1. 提炼 3-5 个核心要点，按重要性排序
2. 使用中文输出
3. 每个要点简洁明了，一句话概括

字幕文本：
{subtitle_text}

请以 JSON 格式输出：
{{"key_points": ["要点1", "要点2", "要点3"]}}
"""


# ── MimoSummarizer ──────────────────────────────────────────────────


class MimoSummarizer(SummarizerClient):
    """MiMo LLM 总结客户端 — 直接调 mimo-v2.5-pro API。"""

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://token-plan-cn.xiaomimimo.com/v1",
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

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

        # 构造 prompt
        prompt = _PROMPT_TEMPLATE.format(subtitle_text=text)

        # 调 mimo-v2.5-pro API
        try:
            resp = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "mimo-v2.5-pro",
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=30,
            )
        except httpx.TimeoutException:
            raise LLMError("llm_timeout")
        except httpx.RequestError as e:
            raise LLMError("llm_network_error", str(e))

        if resp.status_code != 200:
            raise LLMError("llm_api_error", f"{resp.status_code}: {resp.text[:200]}")

        content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")

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
