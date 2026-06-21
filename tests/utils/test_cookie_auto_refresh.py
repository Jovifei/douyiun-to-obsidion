"""Test src/utils/cookie_probe.py — probe_and_rotate cookie 过期检测 + 自动轮转。

TDD: 5 tests covering:
1. test_probe_and_rotate_exists — probe_and_rotate 函数存在且签名正确
2. test_valid_cookie_returns_true — cookie 有效 → 返回 True，不轮换
3. test_expired_rotate_from_backup — cookie 过期 + 备份目录有更旧有效 cookies → 自动替换，返回 True
4. test_all_expired_returns_false — 全部 cookie 过期 → 返回 False
5. test_backup_dir_missing_skips_rotation — backup_dir 不存在 → 跳过轮换
"""
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


class TestProbeAndRotateExists:
    """probe_and_rotate 函数存在且签名正确。"""

    def test_function_exists_and_callable(self):
        from src.utils.cookie_probe import probe_and_rotate
        assert callable(probe_and_rotate)

    def test_function_signature(self):
        import inspect
        from src.utils.cookie_probe import probe_and_rotate

        sig = inspect.signature(probe_and_rotate)
        params = list(sig.parameters.keys())
        assert params == ["cookies_path", "backup_dir"]
        assert sig.return_annotation in (bool, "bool")


class TestValidCookieReturnsTrue:
    """cookie 有效（HTTP 200）→ 返回 True，不轮换。"""

    @patch("src.utils.cookie_probe.httpx")
    def test_valid_cookie_no_rotation(self, mock_httpx, tmp_path):
        from src.utils.cookie_probe import probe_and_rotate

        cookies_file = tmp_path / "cookies.txt"
        cookies_file.write_text(
            "example.com\tTRUE\t/\tFALSE\t0\ttoken\tvalid123\n"
        )
        backup_dir = tmp_path / "backups"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_httpx.Client.return_value.__enter__.return_value.get.return_value = (
            mock_response
        )

        result = probe_and_rotate(
            cookies_path=str(cookies_file),
            backup_dir=str(backup_dir),
        )

        assert result is True
        # 验证没有创建 backup_dir
        assert not backup_dir.exists()
        # 验证 cookies 文件内容未被修改
        assert "valid123" in cookies_file.read_text(encoding="utf-8")


class TestExpiredRotateFromBackup:
    """cookie 过期 + 备份目录有更旧有效 cookies → 自动替换，返回 True。"""

    @patch("src.utils.cookie_probe.httpx")
    def test_expired_rotate_with_valid_backup(self, mock_httpx, tmp_path):
        from src.utils.cookie_probe import probe_and_rotate

        # 主 cookies 文件（过期）
        cookies_file = tmp_path / "cookies.txt"
        cookies_file.write_text(
            "example.com\tTRUE\t/\tFALSE\t0\ttoken\texpired_token\n"
        )

        # 备份目录 + 有效备份
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        valid_backup = backup_dir / "cookies_backup_20260601.txt"
        valid_backup.write_text(
            "example.com\tTRUE\t/\tFALSE\t0\ttoken\tfresh_token_999\n"
        )

        call_count = [0]

        def mock_get(url, **kwargs):
            call_count[0] += 1
            resp = MagicMock()
            # 第一次调用（probe 主 cookies）→ 401
            # 第二次调用（probe 备份 cookies）→ 200
            if call_count[0] == 1:
                resp.status_code = 401
            else:
                resp.status_code = 200
            return resp

        mock_httpx.Client.return_value.__enter__.return_value.get.side_effect = mock_get

        result = probe_and_rotate(
            cookies_path=str(cookies_file),
            backup_dir=str(backup_dir),
        )

        assert result is True
        # 验证 cookies 文件已被替换为备份内容
        content = cookies_file.read_text(encoding="utf-8")
        assert "fresh_token_999" in content


class TestAllExpiredReturnsFalse:
    """全部 cookie 过期（主文件和所有备份都无效）→ 返回 False。"""

    @patch("src.utils.cookie_probe.httpx")
    def test_all_expired_returns_false(self, mock_httpx, tmp_path):
        from src.utils.cookie_probe import probe_and_rotate

        cookies_file = tmp_path / "cookies.txt"
        cookies_file.write_text(
            "example.com\tTRUE\t/\tFALSE\t0\ttoken\texpired_token\n"
        )

        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        backup1 = backup_dir / "cookies_backup_20260601.txt"
        backup1.write_text(
            "example.com\tTRUE\t/\tFALSE\t0\ttoken\talso_expired_1\n"
        )
        backup2 = backup_dir / "cookies_backup_20260501.txt"
        backup2.write_text(
            "example.com\tTRUE\t/\tFALSE\t0\ttoken\talso_expired_2\n"
        )

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_httpx.Client.return_value.__enter__.return_value.get.return_value = (
            mock_response
        )

        result = probe_and_rotate(
            cookies_path=str(cookies_file),
            backup_dir=str(backup_dir),
        )

        assert result is False
        # 验证原始内容未被修改
        assert "expired_token" in cookies_file.read_text(encoding="utf-8")


class TestBackupDirMissingSkipsRotation:
    """backup_dir 不存在 → 跳过轮换，正常 probe 主 cookies。"""

    @patch("src.utils.cookie_probe.httpx")
    def test_missing_backup_dir_skips_rotation(self, mock_httpx, tmp_path):
        from src.utils.cookie_probe import probe_and_rotate

        cookies_file = tmp_path / "cookies.txt"
        cookies_file.write_text(
            "example.com\tTRUE\t/\tFALSE\t0\ttoken\texpired_token\n"
        )
        backup_dir = tmp_path / "nonexistent_backups"

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_httpx.Client.return_value.__enter__.return_value.get.return_value = (
            mock_response
        )

        result = probe_and_rotate(
            cookies_path=str(cookies_file),
            backup_dir=str(backup_dir),
        )

        # cookie 过期 + 无备份 → False
        assert result is False
        # 验证 backup_dir 仍然不存在
        assert not backup_dir.exists()
