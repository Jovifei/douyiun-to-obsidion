"""Test batch URL extraction — M5 Task 5.

Spec ref: openspec/changes/m5-multichannel-batch/specs/batch-url/spec.md
- extract_all_urls(text) 提取所有已识别平台 URL
- 支持抖音/B站/小红书/YouTube
- 去重 + 保持顺序
"""
import pytest

from src.extractors.batch_url import extract_all_urls


class TestExtractAllUrls:
    """extract_all_urls 从文本中提取所有支持平台的 URL。"""

    def test_single_douyin_url(self):
        """单条抖音 URL → 返回 [url]"""
        text = "看看这个 https://www.douyin.com/video/7234567890123"
        result = extract_all_urls(text)
        assert result == ["https://www.douyin.com/video/7234567890123"]

    def test_three_douyin_urls(self):
        """3 条不同抖音 URL → 返回 [url1, url2, url3]"""
        text = (
            "第一个 https://www.douyin.com/video/111\n"
            "第二个 https://www.douyin.com/video/222\n"
            "第三个 https://www.douyin.com/video/333"
        )
        result = extract_all_urls(text)
        assert len(result) == 3
        assert "111" in result[0]
        assert "222" in result[1]
        assert "333" in result[2]

    def test_mixed_platform_urls(self):
        """混合平台 URL（抖音 + Bilibili + YouTube）→ 返回全部"""
        text = (
            "抖音 https://www.douyin.com/video/111 "
            "B站 https://www.bilibili.com/video/BV1234 "
            "YouTube https://www.youtube.com/watch?v=abc123"
        )
        result = extract_all_urls(text)
        assert len(result) == 3
        assert any("douyin.com" in u for u in result)
        assert any("bilibili.com" in u for u in result)
        assert any("youtube.com" in u for u in result)

    def test_no_valid_urls(self):
        """消息无有效 URL → 返回空 list"""
        text = "今天天气不错，没有链接"
        result = extract_all_urls(text)
        assert result == []

    def test_emoji_and_command_text_with_url(self):
        """消息含 emoji + 口令 + URL → 只提取 URL"""
        text = "9.99 复制打开抖音，看看【作者】的作品 https://v.douyin.com/iAbCdEf/ 🔥"
        result = extract_all_urls(text)
        assert len(result) == 1
        assert "v.douyin.com" in result[0]

    def test_xiaohongshu_url(self):
        """小红书 URL → 返回该 URL"""
        text = "小红书笔记 https://www.xiaohongshu.com/explore/abc123"
        result = extract_all_urls(text)
        assert len(result) == 1
        assert "xiaohongshu.com" in result[0]

    def test_dedup_preserves_order(self):
        """重复 URL 去重 + 保持首次出现顺序"""
        text = (
            "第一个 https://www.douyin.com/video/111 "
            "重复 https://www.douyin.com/video/111 "
            "第三个 https://www.douyin.com/video/333"
        )
        result = extract_all_urls(text)
        assert len(result) == 2
        assert "111" in result[0]
        assert "333" in result[1]

    def test_unsupported_platform_filtered(self):
        """不支持的平台 URL（如淘宝）→ 被过滤"""
        text = (
            "抖音 https://www.douyin.com/video/111 "
            "淘宝 https://item.taobao.com/item.htm?id=123"
        )
        result = extract_all_urls(text)
        assert len(result) == 1
        assert "douyin.com" in result[0]

    def test_short_douyin_url(self):
        """抖音短链 → 也被提取"""
        text = "短链 https://v.douyin.com/abc123/"
        result = extract_all_urls(text)
        assert len(result) == 1
        assert "v.douyin.com" in result[0]

    def test_bilibili_short_url(self):
        """B站短链 → 也被提取"""
        text = "B站短链 https://b23.tv/abc123"
        result = extract_all_urls(text)
        assert len(result) == 1
        assert "b23.tv" in result[0]

    def test_youtube_short_url(self):
        """YouTube 短链 → 也被提取"""
        text = "YouTube https://youtu.be/abc123"
        result = extract_all_urls(text)
        assert len(result) == 1
        assert "youtu.be" in result[0]

    def test_xiaohongshu_short_url(self):
        """小红书短链 → 也被提取"""
        text = "小红书短链 https://xhslink.com/abc123"
        result = extract_all_urls(text)
        assert len(result) == 1
        assert "xhslink.com" in result[0]
