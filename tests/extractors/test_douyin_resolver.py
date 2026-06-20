"""Test douyin URL resolver.

Spec ref: specs/douyin-extraction/spec.md
- Scenario: 短链解析
- Scenario: 分享文案解析
- Scenario: 非抖音 URL
"""
import pytest

from src.extractors.douyin_resolver import resolve_url, ResolverError


def test_short_url_resolves(monkeypatch):
    """WHEN 收到 https://v.douyin.com/iAbCdEf/
    THEN 302 跟随得完整 URL，提取 video_id，返回 source_url_type='short'。"""

    def fake_follow_redirect(url):
        return "https://www.douyin.com/video/7234567890123"

    monkeypatch.setattr(
        "src.extractors.douyin_resolver._follow_redirect", fake_follow_redirect
    )
    result = resolve_url("https://v.douyin.com/iAbCdEf/")
    assert result["video_id"] == "7234567890123"
    assert result["source_url_type"] == "short"
    assert "douyin.com/video/7234567890123" in result["canonical_url"]


def test_full_url_no_redirect():
    """WHEN 收 https://www.douyin.com/video/7234567890123
    THEN 不跟 302，直接提取 video_id，type='full'。"""
    result = resolve_url("https://www.douyin.com/video/7234567890123")
    assert result["video_id"] == "7234567890123"
    assert result["source_url_type"] == "full"


def test_iesdouyin_url():
    """WHEN 收 https://www.iesdouyin.com/share/video/7234567890123
    THEN type='iesdouyin'。"""
    result = resolve_url("https://www.iesdouyin.com/share/video/7234567890123")
    assert result["video_id"] == "7234567890123"
    assert result["source_url_type"] == "iesdouyin"


def test_share_text_extracts_url(monkeypatch):
    """WHEN 收分享文案含短链
    THEN 提取短链后按短链流程解析，忽略 emoji 与口令。"""
    monkeypatch.setattr(
        "src.extractors.douyin_resolver._follow_redirect",
        lambda u: "https://www.douyin.com/video/7234567890123",
    )
    text = "9.99 复制打开抖音，看看【作者】的作品 https://v.douyin.com/iAbCdEf/ 🔥"
    result = resolve_url(text)
    assert result["video_id"] == "7234567890123"
    assert result["source_url_type"] == "short"


def test_non_douyin_url_raises():
    """WHEN 收 https://www.bilibili.com/video/BVxxx
    THEN 抛 ResolverError('not_douyin_url')。"""
    with pytest.raises(ResolverError) as exc:
        resolve_url("https://www.bilibili.com/video/BVxxx")
    assert "not_douyin_url" in str(exc.value)
