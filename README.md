# Hermes Tool

macOS 桌面状态栏灵动岛工具，配合 Hermes Agent 使用。

它会在桌面悬浮显示 Hermes 当前状态、动作、涉及文件、定时任务状态、错误信息等，
让你不用切终端、切 Telegram、切日志，就能直接看到 Hermes 现在在干什么。

## 它能干什么

### 实时状态显示
读取 Hermes 本地运行状态，显示当前动作中文文案，例如：
- 正在读取文件: xxx
- 正在执行 shell 命令
- 正在修改文件
- 正在打开网页
- 正在等待模型响应
- 正在整理上下文
- 已读取文件 / 已执行 shell 命令 / 已更新任务清单

状态感知优先使用 `~/.hermes/runtime/live_activity.json` 实时通道，
回退到 `~/.hermes/state.db` 会话消息。

### 状态分类与健康感知
- working / thinking / waiting / idle / error
- 完成摘要：待命时显示「刚完成: xxx」
- 卡住检测：长时间无进展时提示「疑似卡住」
- cron 超时检测

### 定时任务监控
- 读取 `~/.hermes/cron/jobs.json`
- 显示任务名、下次运行、最近结果、错误
- 支持右键菜单暂停/恢复/立即触发

### 状态栏图标同步变色
- working -> 绿灯
- waiting -> 紫灯
- thinking -> 橙灯
- idle -> 灰灯
- error -> 红灯

### 自动收拢
鼠标 10 秒未悬停时，灵动岛平滑收拢成小圆球（仅保留状态灯），
鼠标移入圆球后平滑恢复。可通过右键菜单「自动收拢」开关控制。

### 其他
- 展开详情任务卡片（动作、文件、任务、下次运行、模型、会话）
- 最近动作面板（可右键开关）
- 最近消息面板
- 性能统计面板
- 系统托盘菜单
- 深色/浅色主题
- macOS 桌面通知

## 环境要求

- macOS
- Python 3
- PyQt5
- pyobjc
- 本机已安装并运行过 Hermes Agent

## 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install PyQt5 pyobjc
```

## 启动方式

```bash
python3 hermes_pet_v3.py
```

## 主要文件

- `hermes_pet_v3.py`：主程序
- `hermes_pet.icns`：图标
- `CHANGELOG_v3.1.md`：版本更新说明
- `OPTIMIZATION_v3.md`：功能与优化说明
- `requirements.txt`：依赖列表

## 说明

这个工具优先保证：
1. 状态检测准确
2. 文案表达清楚
3. cron / 自动推进可观测
4. 桌面交互稳定

不优先做复杂动画或花哨交互。

适合用于：
- 本机跑 Hermes CLI / gateway / cron
- 希望不打开终端也能看到 Hermes 状态
- 做自动推进、定时任务、代码修改、浏览器自动化

## License

MIT
