# Hermes Tool

一个给 Hermes Agent 用的 macOS 桌面灵动岛/桌宠状态工具。

它会在桌面悬浮显示 Hermes 当前状态，核心目标不是“做个会动的小玩具”，而是让你在不盯终端、不切 Telegram、不翻日志的情况下，直接看到 Hermes 现在在干什么、有没有卡住、定时任务是否正常、最近动了哪些文件。

## 这是什么

这是一个基于 PyQt5 的桌面状态浮层工具，主要用于配合 Hermes Agent 使用。

它会读取 Hermes 本地运行状态，包括：
- `~/.hermes/runtime/live_activity.json`
- `~/.hermes/runtime/live_activity.log.jsonl`
- `~/.hermes/runtime/pet_status_debug.log`
- `~/.hermes/cron/jobs.json`
- `~/.hermes/state.db`

然后把这些状态整理成桌面上的灵动岛式状态提示。

## 它能干什么

### 1. 实时显示 Hermes 当前动作
例如：
- 正在读取文件
- 正在执行 shell 命令
- 正在修改文件
- 正在打开网页
- 正在派发子任务
- 正在等待模型响应
- 正在接收模型响应
- 已读取文件 / 已执行 shell 命令 / 已更新任务清单

不是简单显示一坨原始 tool 名，而是尽量翻译成人能一眼看懂的状态文案。

### 2. 识别 Hermes 是否真的在工作
工具会区分：
- working：当前确实有活跃动作
- thinking：正在思考/等待模型
- waiting：当前待命
- idle：空闲
- error：异常或超时

并且对“刚完成的事件”和“过期的 live activity”做了衰减处理，避免明明没活还一直亮绿灯。

### 3. 监控 cron / 自动推进任务
会读取 `~/.hermes/cron/jobs.json`，显示：
- 当前相关任务名
- 上次执行结果
- 上次执行时间
- 下次执行时间
- 是否超时
- 是否存在 delivery error / last error

适合无人值守自动推进时做桌面监控。

### 4. 展示最近动作与相关文件
会尽量提炼：
- 最近执行了什么
- 最近改了哪些文件
- 最近是不是在做 round prompt / 验证 / 构建 / 归档

更适合开发流而不是普通聊天气泡展示。

### 5. 悬浮桌面显示，减少切换成本
支持：
- 灵动岛风格状态展示
- 展开查看详细信息
- 系统托盘驻留
- 智能缩进/自动收起
- 主题和透明度配置

## 适用场景

- 你在本机跑 Hermes CLI / gateway / cron
- 你希望不打开终端也能知道 Hermes 当前状态
- 你在做自动推进、定时任务、代理编排、代码修改、浏览器自动化
- 你希望桌面状态条展示“正在做什么”而不是只有一个抽象的 busy 指示灯

## 当前特性

- 基于 runtime live activity 的实时状态显示
- cron 自动推进健康状态监控
- SQLite `state.db` 会话/消息回退读取
- 更友好的 completed 事件中文化文案
- stale activity 过期处理，避免假活跃
- 历史消息 / 性能面板 / 状态扩展信息
- macOS 通知与托盘支持

## 运行环境

- macOS
- Python 3
- PyQt5
- 本机已安装并运行过 Hermes Agent

## 安装依赖

建议先创建虚拟环境，然后安装：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install PyQt5 pyobjc
```

如果只需要基础界面显示，通常 PyQt5 是必须的；某些 macOS 通知/系统集成功能依赖 `pyobjc`。

## 启动方式

```bash
cd "~/Desktop/cursor/hermes 桌宠"
python3 hermes_pet_v3.py
```

## 主要文件

- `hermes_pet_v3.py`：主程序
- `hermes_pet.icns`：图标资源
- `CHANGELOG_v3.1.md`：版本更新说明
- `OPTIMIZATION_v3.md`：功能与优化说明

## 说明

这个仓库的重点是“让 Hermes 的运行状态变得可视化、可理解、可监控”。

优先级是：
1. 状态检测准确
2. 文案表达清楚
3. cron / 自动推进可观测
4. 桌面交互稳定

而不是优先做复杂动画或花哨交互。

## 后续可扩展方向

- 更完整的 Hermes 实时事件总线接入
- 更精细的工具类型映射
- 更准确的任务阶段推断
- 打包发布 `.app`
- 针对 Telegram / cron / browser / patch / delegate_task 做更细文案

## License

MIT
