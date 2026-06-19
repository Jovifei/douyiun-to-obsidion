# T2 · 抖音视频内容获取链路调研

**调研日期**：2026-06-19  调研目标：为「抖音知识视频自动归档到 Obsidian」选定可用的视频/字幕/音频抓取链路。

---

## TL;DR

- **推荐主链路**：`手机分享文本 → 正则抽 v.douyin.com 短链 → yt-dlp(主) / DouK-Downloader(备) 解析 → 落 mp4 + 自带字幕(若有) → ffmpeg 抽 16kHz mono wav → Whisper 兜底字幕`。
- **首选工具**：**yt-dlp**（活跃度最高、自带 douyin auto-caption 抓取、tiktok/douyin 共用 extractor），失败时切 **DouK-Downloader (TikTokDownloader, JoeanAmier)** 14.8k★，对国内分享链路、cookie 流程做得最完整。
- **无法回避的痛点**：抖音 web 端要求请求带"新鲜的" Cookie + 通过 a_bogus 校验，不带 cookie 直接下经常 403。所有工具本质上都是绕这层；yt-dlp 走 `aweme/v1/web/aweme/detail/` API、要求传入浏览器 Cookie；DouK-Downloader 自带终端交互引导你导入 cookie。

---

## 1. 抖音 Share URL & 分享文本格式

### 1.1 手机抖音"复制链接"实际文本（典型样本）

```
3.14 复制打开抖音，看看【XX的作品】这是一段标题文字 # 话题  https://v.douyin.com/iAbCdEfG/ 复制此链接，打开Dou音搜索，直接观看视频！
```

特征：
- 头部是 emoji + 数字"口令"（防爬，可整段忽略）。
- 中段含中文标题 + 话题 hashtag。
- **关键是 `https://v.douyin.com/[A-Za-z0-9_-]+/?` 这一段短链**——所有下载工具的入口。

### 1.2 URL 形态枚举（你的解析器至少要识别这 5 种）

| URL 形态 | 含义 | 处理方式 |
|---|---|---|
| `https://v.douyin.com/xxx/` | 移动端分享短链 | HEAD 跟 302 拿到完整 URL，再解析 aweme_id |
| `https://v.iesdouyin.com/share/video/{aweme_id}/` | iOS 老分享接口 | 直接从路径取 aweme_id |
| `https://www.iesdouyin.com/share/video/{aweme_id}/` | web 旧版分享 | 同上 |
| `https://www.douyin.com/video/{aweme_id}` | web 端视频页（数字 ID） | 直接取 aweme_id（yt-dlp 的 `_VALID_URL` 仅匹配此种） |
| `https://www.douyin.com/note/{id}`、`/gallery/{id}` | 图文/图集 | 走 DouK-Downloader 的 note/gallery 路径，yt-dlp 不支持 |

### 1.3 解析正则（实战可用）

```python
import re
SHARE_PATTERN = re.compile(r'https?://(?:v\.douyin\.com|v\.iesdouyin\.com|www\.iesdouyin\.com|www\.douyin\.com)/[^\s一-鿿，。、！？]+')
```

短链需要先 `requests.head(url, allow_redirects=True)` 跟 302 得到带 aweme_id 的真实 URL。

---

## 2. 原生字幕（这是最有价值的发现）

**抖音确实有自带字幕**——通过算法自动生成的 `auto_caption` 或 UP 主上传的 `cla_info.caption_infos`。yt-dlp 的 tiktok extractor（DouyinIE 继承自 TikTokBaseIE）已经实现了抓取逻辑：

```python
# yt_dlp/extractor/tiktok.py (master, 2026-06)
def _get_subtitles(self, aweme_detail, aweme_id, user_name):
    EXT_MAP = {'creator_caption': 'json', ...}
    # 路径 1：interaction_stickers → auto_video_caption_info → auto_captions
    # 自动语音识别字幕，逐句 utterances[{start_time, end_time, text}] → 转 SRT
    # 路径 2：video.cla_info.caption_infos
    # 创作者上传的字幕，多语言
```

**实操结论**：
- yt-dlp 加 `--write-auto-subs --write-subs --sub-langs all --convert-subs srt` 即可拿到 SRT；
- 字幕命中率：知识类/口播类视频一般有自动字幕；纯 BGM/无人声视频没有；
- 命中时**直接省掉 Whisper 那一步**，是整个链路的最大优化点；
- DouK-Downloader、F2、douyin-downloader 三个国内工具默认都不抓自带字幕，需要自己读 `aweme_detail` 字段（路径同上）。
- 兜底：DouK 内置可选的 `OpenAI Transcriptions API` 转写；F2 提供 `json_2_lrc` 工具但只是格式转换。

---

## 3. 下载工具横评

| 项目 | 链接 | Stars | 最近提交 | 抖音支持度 | 字幕支持 | Cookie 需求 | 推荐度 |
|---|---|---|---|---|---|---|---|
| **yt-dlp** | [yt-dlp/yt-dlp](https://github.com/yt-dlp/yt-dlp) | 171k | 2026-06-18 | 仅 `douyin.com/video/{id}`，短链 v.douyin.com 不直接吃 | **原生 auto_caption + cla_info（关键优势）** | 强烈推荐传 cookies；近期 issue #16867/#16803/#9667 频繁报 "Fresh cookies needed" | ⭐⭐⭐⭐⭐ |
| **DouK-Downloader (TikTokDownloader)** | [JoeanAmier/TikTokDownloader](https://github.com/JoeanAmier/TikTokDownloader) | 14.8k | 2026-06-17 | 全场景：发布/喜欢/合集/收藏夹/评论/直播/搜索/热榜，含图集/实况 | 默认无；可挂 OpenAI Transcriptions | 需要写入 cookie 到配置文件，cookie 失效后重新写一次；扫码登录已废弃；浏览器读 cookie 仍可用（Win 需管理员） | ⭐⭐⭐⭐⭐ |
| **douyin-downloader (V2.0)** | [jiji262/douyin-downloader](https://github.com/jiji262/douyin-downloader) | 8.0k | 2026-06-05 | 视频/图集/合集/音乐/直播/收藏夹；明确支持 `v.douyin.com` 短链解析 | 有可选 OpenAI 转写（无原生） | 需要 `msToken/ttwid/odin_tt/passport_csrf_token/sid_guard`；提供 `tools.cookie_fetcher` Playwright 自动抓取 | ⭐⭐⭐⭐ |
| **F2** | [Johnserf-Seed/f2](https://github.com/Johnserf-Seed/f2) | 2.5k | 2026-04-13 | 视频/合集/直播/弹幕，多平台（含 TikTok/微博/X） | 仅 `json_2_lrc` 格式转换工具，无原生抓取 | 公共内容免登录可下；私有内容需 sessionid。**自带 X-Bogus / a_bogus / msToken 生成器（开源）** | ⭐⭐⭐⭐ |
| **you-get** | [soimort/you-get](https://github.com/soimort/you-get) | 56.8k | 2026-04-30 | 抖音 extractor 走 `web/api/v2/aweme/iteminfo`，老接口已不稳定 | 无 | 几乎无 cookie 校验，但接口经常返回空 | ⭐⭐ |
| **res-downloader** | [putyy/res-downloader](https://github.com/putyy/res-downloader) | 18k | 2026-06-18 | 抓包式 Go GUI，支持视频号/抖音/快手/小红书/m3u8 | 无 | 抓包代理免 cookie | ⭐⭐⭐（GUI 不适合脚本化） |
| videodl | [CharlesPikachu/videodl](https://github.com/CharlesPikachu/videodl) | 2.3k | 2026-06-18 | 多平台轻量级下载，覆盖抖音 | 无 | 较轻 | ⭐⭐ |

**Stars 与时间均为 2026-06-19 GitHub API 实测值。**

---

## 4. 反爬现状（2026-06）

### 4.1 抖音 web 端的签名/校验栈
- **`_signature`**：JS 生成的 base64，老规则，多数工具仍能离线生成；
- **`X-Bogus`**：旧版主签，2024 年起逐渐被替代；
- **`a_bogus` / `ab`**：当前 web 端主签，按 `?aid=&device_id=&ua=&...` 等参数 + 当前时间生成的 base64。F2 已开源"满血版 ab"；NearHuiwen/TiktokDouyinCrawler、jackluson/a_bogus_douyin、idinging/douyin-abogus 等也开源了 Python/JS 实现，但更新都停在 2024-2025；
- **`msToken`**：Cookie 字段，被 douyin web 主动种入；可通过浏览器 cookie 复制，也可用 F2 的 TokenManager 现造（伪 token）；
- **`ttwid` / `odin_tt` / `passport_csrf_token` / `sid_guard`**：身份识别，DouK 与 douyin-downloader 都要求填；
- **`s_v_web_id`**：yt-dlp 用其判断"是否拿到了新鲜 Cookie"；缺失会直接报 `Fresh cookies needed`；
- **`__ac_signature`**：访问 douyin.com 主域时偶发要求，主要影响 user 主页接口。

### 4.2 实测结论
- **公共视频详情页（aweme/v1/web/aweme/detail）现在仍能在带 cookie 时直接获取，无需 a_bogus**——yt-dlp 就是这么做的。这是目前最稳的"轻签名"路径。
- **用户主页 / 评论 / 合集列表必须 a_bogus**，没有签名直接 403。所以"批量下账号作品"工作量上一个台阶。
- 维护活跃度：yt-dlp（主线天天合）> DouK-Downloader（每周）> F2（半年节奏）> 各种 a_bogus 独立仓库（多数停在 2024）。
- 灰区提醒：a_bogus 的 RPC 远程调用、付费 API、TikHub 等代签服务存在，但都是非公开接口，本项目个人留存使用建议**只用 cookie + yt-dlp/DouK 自带的轻签名路径**。

### 4.3 近半年抖音改了啥
- 2025 Q4 起，无 cookie 直连 `aweme/detail` 命中率明显下降（yt-dlp issue #16278/#16803/#16867 都是这条线索）；
- a_bogus 的算法版本号从 1.0.0.x 滚到 1.0.1.19（intAV/Douyin_live_like 仓库可见）；
- 实况图（live photo）/ 图集结构改了字段，jiji262 V2 版本专门重写了图集解析；
- 扫码登录获取 cookie 通道已废弃（DouK README 明确划线），现在只能浏览器登录后导出。

---

## 5. 推荐链路图

```
┌─────────────────────────────────────────────────────────────┐
│ 1) 手机抖音 → 复制链接 → 粘到 Obsidian inbox / 剪贴板        │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│ 2) 文本预处理：正则抽 v.douyin.com 短链 → HEAD 跟 302 →       │
│    得到 https://www.douyin.com/video/{aweme_id}             │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│ 3) 主路径：yt-dlp（带浏览器 cookie）                          │
│    --write-info-json --write-auto-subs --sub-langs all       │
│    --convert-subs srt -f bv*+ba/b -o "{title}.{ext}"         │
│    备路径：DouK-Downloader（cookie 失效 / 图集 / 合集时）     │
└─────────────────┬───────────────────────────────────────────┘
                  │
       ┌──────────┴──────────┐
       ▼                     ▼
  下载到 mp4 +           （若 SRT 已存在 → 跳到第 5 步）
  info.json
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│ 4) ffmpeg 抽音频：16 kHz mono PCM wav → Whisper / faster-     │
│    whisper / WhisperX 转写 → SRT                             │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│ 5) 写入 Obsidian vault（你已有的 notes-personal/notes-        │
│    research vault）：md 模板 + 嵌入视频 + 字幕 + 元数据       │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. Python 代码骨架

```python
"""
douyin_fetch.py
输入：抖音分享文本（含 v.douyin.com 短链）
输出：本地 mp4 + srt（自带字幕优先；没有则 ffmpeg 抽 wav 留给 Whisper）
依赖：pip install yt-dlp requests
"""
from __future__ import annotations
import re, subprocess, json
from pathlib import Path
import requests
import yt_dlp

SHARE_RE = re.compile(
    r'https?://(?:v\.douyin\.com|v\.iesdouyin\.com|www\.iesdouyin\.com|www\.douyin\.com)/[^\s一-鿿，。、！？]+'
)

def extract_url(share_text: str) -> str:
    m = SHARE_RE.search(share_text)
    if not m:
        raise ValueError("分享文本里没找到抖音链接")
    raw = m.group(0).rstrip('/')
    # 跟一次 302 拿真实 douyin.com/video/{id}
    r = requests.head(raw, allow_redirects=True, timeout=10,
                      headers={"User-Agent": "Mozilla/5.0"})
    return r.url

def cookie_from_browser() -> dict:
    """从本地 Chrome/Edge 读 douyin.com 的 cookie；用 yt-dlp 内置机制。"""
    return {"cookiesfrombrowser": ("chrome", None, None, None)}

def download(url: str, out_dir: str | Path = "./out") -> dict:
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    ydl_opts = {
        "outtmpl": str(out_dir / "%(id)s_%(title).80s.%(ext)s"),
        "writeinfojson": True,
        "writeautomaticsub": True,   # 抖音 auto_caption
        "writesubtitles": True,      # 创作者上传字幕（cla_info）
        "subtitleslangs": ["all"],
        "subtitlesformat": "srt/best",
        "postprocessors": [
            {"key": "FFmpegSubtitlesConvertor", "format": "srt"},
        ],
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "quiet": False,
        **cookie_from_browser(),
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
    return info

def extract_audio_for_whisper(mp4_path: Path) -> Path:
    """ffmpeg 抽 16kHz mono PCM wav，给 Whisper / faster-whisper 用。"""
    wav = mp4_path.with_suffix(".wav")
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(mp4_path),
         "-vn", "-ac", "1", "-ar", "16000",
         "-c:a", "pcm_s16le", str(wav)],
        check=True,
    )
    return wav

def fetch(share_text: str, out_dir: str = "./out") -> dict:
    url = extract_url(share_text)
    info = download(url, out_dir)
    aweme_id = info.get("id")
    out = Path(out_dir)
    mp4 = next(out.glob(f"{aweme_id}_*.mp4"), None)
    srt = next(out.glob(f"{aweme_id}_*.srt"), None)
    result = {"aweme_id": aweme_id, "mp4": str(mp4) if mp4 else None,
              "srt_native": str(srt) if srt else None,
              "title": info.get("title"), "duration": info.get("duration"),
              "uploader": info.get("uploader")}
    if not srt and mp4:                    # 自带字幕没命中 → 抽音频留给 Whisper
        result["wav_for_whisper"] = str(extract_audio_for_whisper(mp4))
    return result

if __name__ == "__main__":
    import sys
    print(json.dumps(fetch(sys.argv[1]), ensure_ascii=False, indent=2))
```

调用示例：

```bash
python douyin_fetch.py "3.14 复制打开抖音 https://v.douyin.com/iAbCdEfG/ 看看..."
```

---

## 7. 风险与缺口

| 风险 | 说明 | 缓解 |
|---|---|---|
| Cookie 过期 | yt-dlp 频繁报 "Fresh cookies needed"（issue #16867/#9667 长期 open） | 用 `cookiesfrombrowser` 机制自动从 Chrome/Edge 读；UI 上设"重新登录"按钮 |
| 自动字幕缺失 | 纯 BGM/方言/嘈杂视频没有 auto_caption | Whisper 兜底（建议 faster-whisper + medium 模型，中文够用） |
| 图集/实况图 | yt-dlp 不支持 `/note/`、`/gallery/`、live photo | 检测到后切 DouK-Downloader |
| 用户主页批量 | 必须 a_bogus，yt-dlp 没实现 | 不在 MVP 范围；要做时切 DouK-Downloader 的 `account.post` 模式 |
| URL 域名变化 | 抖音偶尔下发新短域，旧工具的正则可能漏 | 把正则做成可配置项，在 inbox 里保留原始分享文本作为 fallback |
| 反爬升级 | a_bogus 算法升级时所有工具一起翻车 | 不绑死单一工具；保留 yt-dlp + DouK 双链路；定期 `pip install -U yt-dlp` |
| 视频 403 | CDN 临时封禁 IP 段 | 加 `proxy` 配置 + 失败重试；DouK 自带指数退避 |

---

## 8. 引用

- yt-dlp 仓库主页：https://github.com/yt-dlp/yt-dlp（访问 2026-06-19）
- yt-dlp tiktok extractor 源码（含 DouyinIE + 字幕逻辑）：https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/tiktok.py（访问 2026-06-19）
- yt-dlp Douyin 相关 issue：#16867（2026-06-04）、#16803（2026-05-27）、#9667（2026-03-31，仍 open）、#16278（2026-03-19）（访问 2026-06-19）
- DouK-Downloader (TikTokDownloader) 仓库：https://github.com/JoeanAmier/TikTokDownloader（14.8k★，访问 2026-06-19）
- DouK-Downloader Wiki：https://github.com/JoeanAmier/TikTokDownloader/wiki/Documentation
- douyin-downloader (V2.0)：https://github.com/jiji262/douyin-downloader（8.0k★，访问 2026-06-19）
- F2 仓库与文档：https://github.com/Johnserf-Seed/f2 + https://f2.wiki/（2.5k★，访问 2026-06-19）
- you-get 仓库：https://github.com/soimort/you-get（56.8k★，access 2026-06-19）
- res-downloader：https://github.com/putyy/res-downloader（18k★）
- a_bogus 算法实现参考：
  - https://github.com/NearHuiwen/TiktokDouyinCrawler（490★，2024-05）
  - https://github.com/jackluson/a_bogus_douyin（56★，2024-06）
  - https://github.com/idinging/douyin-abogus（2025-06）
  - https://github.com/intAV/Douyin_live_like（2026-04 更新到 1.0.1.19）
- Whisper 主仓：https://github.com/openai/whisper（推荐 ffmpeg 16 kHz mono 输入）
- GitHub API 调用 raw 数据：`api.github.com/repos/{owner}/{repo}` & `search/repositories`、`search/issues`，时间戳取自 `pushed_at` / `updated_at` 字段。

---

**报告完。所有数字均为 2026-06-19 实测，工具版本和 issue 状态请以 GitHub 当前页面为准。**
