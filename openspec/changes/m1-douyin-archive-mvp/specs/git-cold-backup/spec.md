## ADDED Requirements

### Requirement: vault Git 仓库初始化

系统 SHALL 在 `vault_root` 目录 `git init`，配置默认 user.name/email，提交首条 commit "init: 初始化 Obsidian vault"。

#### Scenario: 首次初始化

- **WHEN** 实施 git-cold-backup 模块时
- **THEN** vault 目录变成 git 仓库，首条 commit 包含除 `.gitignore` 屏蔽外的所有现有文件

### Requirement: .gitignore 屏蔽规则

`vault_root/.gitignore` SHALL 包含以下条目，确保敏感数据与运行时文件不进 Git：

```
# Obsidian 运行时
.obsidian/workspace*
.obsidian/cache/
.obsidian/plugins/*/data.json
.trash/

# 同步冲突
.sync-conflict-*
*.tmp

# 凭证（绝不能进版本控制）
.env
cookies.txt
secrets/
*.key

# 大附件（>50MB 不进 Git，由 Syncthing/iCloud 处理）
attachments/**/*.mp4
attachments/**/*.webm
attachments/**/full-video.*
```

#### Scenario: 屏蔽生效

- **WHEN** 笔记写入 vault
- **THEN** 笔记 `.md` 文件被 git 追踪；`cookies.txt` / `.env` / `*.mp4` 不被追踪

#### Scenario: 不屏蔽 frontmatter 必需字段

- **WHEN** frontmatter `cover_url` 含外部 URL
- **THEN** 该字段值作为字符串存在 `.md` 里，被 git 追踪（不是凭证）

### Requirement: 自动 commit + push 任务计划

系统 SHALL 通过 Windows 任务计划程序注册一个每日定时任务 `douyin-vault-git-backup`，每天 03:00（避开非高峰期）执行：

```powershell
cd E:\AI_Tools\Obsidian\data\notes-personal
git add .
git commit -m "auto: vault backup $(date)"
# push 最多重试 3 次，失败时日志告警但不阻塞下次执行
for i in 1..3 { git push origin main; if ($?) { break } }
```

#### Scenario: 定时执行

- **WHEN** 每天 03:00 触发
- **THEN** 如有未提交变更则 commit + push；无变更则跳过

#### Scenario: push 失败重试

- **WHEN** 首次 push 失败（网络问题）
- **THEN** 重试最多 3 次（间隔 5s），仍失败则记录到 `logs/git-backup/{date}.log`，不阻塞下次执行

### Requirement: 远程仓库地址配置

`vault_root/.git/config` SHALL 配置 `remote.origin.url` 指向 Jovi 选择的私有仓库（GitHub Private 或 Gitee 私仓）。

#### Scenario: 远程仓库就绪

- **WHEN** Jovi 决定仓库地址后（OQ-4 开放问题）
- **THEN** 通过 `git remote add origin <url>` 配置；`git push -u origin main` 首次成功

#### Scenario: 未配置远程仓库时降级

- **WHEN** Jovi 暂未决定远程仓库（M1 实施初期）
- **THEN** 本地 commit 仍正常进行（仅本地版本历史），跳过 push；日志提示"远程仓库未配置，仅本地备份"

### Requirement: commit 信息规范

自动 commit 信息 SHALL 遵循格式 `auto: vault backup YYYY-MM-DD HH:MM:SS (N files changed)`。

#### Scenario: 多文件变更

- **WHEN** 一天内有 12 条新笔记 + 3 处附件更新
- **THEN** 凌晨自动 commit 信息 = `auto: vault backup 2026-06-20 03:00:00 (15 files changed)`

#### Scenario: 零变更跳过

- **WHEN** 一天内无新笔记
- **THEN** **不**产生空 commit，日志记录"no changes to commit"

### Requirement: 不与未来 Syncthing/iCloud 同步冲突

M1 阶段 vault 仅由 Git 追踪。**未来** M4 引入 Syncthing 或 iCloud 时，SHALL 按 DECISIONS A7/A16 约束："同一个 vault 只能有一个主同步通道，Git 作为冷备，其他云盘只能做镜像/只读分发，否则冲突文件污染 vault"。

#### Scenario: 单一主同步通道

- **WHEN** M1 实施时
- **THEN** 仅 Git 作为同步通道，不启用 Syncthing / iCloud

#### Scenario: 为未来扩展留位

- **WHEN** M4 阶段 Jovi 决定启用 Syncthing
- **THEN** M4 change 需评估"Git 与 Syncthing 并存"的冲突风险，本 change 的 `.gitignore` 已排除 `.stfolder` / `.stignore` 等 Syncthing 元数据，避免污染 Git 历史
