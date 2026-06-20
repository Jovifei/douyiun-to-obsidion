"""pytest 公共 fixtures。"""
import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def tmp_db(tmp_path: Path):
    """临时 SQLite 队列 db。"""
    db_path = tmp_path / "test_queue.sqlite3"
    conn = sqlite3.connect(str(db_path))
    yield conn, db_path
    conn.close()


@pytest.fixture
def tmp_vault(tmp_path: Path):
    """临时 vault 目录，模拟 vault root。"""
    vault = tmp_path / "vault"
    (vault / "inbox" / "douyin").mkdir(parents=True, exist_ok=True)
    (vault / "attachments" / "douyin").mkdir(parents=True, exist_ok=True)
    return vault


@pytest.fixture
def sample_short_url():
    """测试用抖音短链（Jovi 提供样本，见 OQ-3）。"""
    return "https://v.douyin.com/iAbCdEf/"


@pytest.fixture
def sample_share_text():
    """测试用分享文案。"""
    return "9.99 复制打开抖音，看看【作者】的作品 https://v.douyin.com/iAbCdEf/ 🔥"
