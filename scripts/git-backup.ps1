<#
.SYNOPSIS
    Obsidian vault git 冷备脚本。
.DESCRIPTION
    cd 到 vault 目录，git add . + commit（有变更才 commit），push 重试 3 次。
    由 Windows 任务计划程序每天 03:00 触发。
.NOTES
    Jovi 待决定远程仓库地址（OQ-4）：暂跳过 push，本地 commit 仍正常。
#>

param(
    [string]$VaultRoot = "E:\AI_Tools\Obsidian\data\notes-personal",
    [int]$MaxRetries = 3
)

$ErrorActionPreference = "Stop"
$Date = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

# 确保 vault 目录存在
if (-not (Test-Path $VaultRoot)) {
    Write-Error "Vault 目录不存在: $VaultRoot"
    exit 1
}

Set-Location $VaultRoot

# 检查是否为 git 仓库
if (-not (Test-Path ".git")) {
    Write-Error "目录不是 git 仓库: $VaultRoot（请先运行 init_vault_git）"
    exit 1
}

# git add 所有变更
git add .
if ($LASTEXITCODE -ne 0) {
    Write-Error "git add 失败"
    exit 1
}

# 检查是否有变更需要 commit
$status = git status --porcelain
if ([string]::IsNullOrWhiteSpace($status)) {
    Write-Host "[$Date] 无变更，跳过 commit"
    exit 0
}

# 统计变更文件数
$changedFiles = ($status | Measure-Object -Line).Lines

# commit
$commitMsg = "auto: vault backup $Date ($changedFiles files changed)"
git commit -m $commitMsg
if ($LASTEXITCODE -ne 0) {
    Write-Error "git commit 失败"
    exit 1
}
Write-Host "[$Date] 已提交: $commitMsg"

# push 重试（Jovi 待决定远程仓库地址（OQ-4））
# 暂跳过 push，仅本地 commit
$remoteUrl = git remote get-url origin 2>$null
if ([string]::IsNullOrWhiteSpace($remoteUrl)) {
    Write-Host "[$Date] 远程仓库未配置，仅本地备份"
    exit 0
}

for ($i = 1; $i -le $MaxRetries; $i++) {
    git push origin main
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[$Date] push 成功（第 $i 次）"
        exit 0
    }
    Write-Warning "[$Date] push 失败（第 $i 次），等待 5 秒后重试..."
    Start-Sleep -Seconds 5
}

Write-Error "[$Date] push 重试 $MaxRetries 次均失败，已放弃"
exit 1
