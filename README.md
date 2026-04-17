# Hermes Tool

macOS 桌面悬浮灵动岛工具，配合 Hermes Agent 使用。

它会在桌面顶部实时显示 Hermes 当前状态、动作、涉及文件、自动任务状态、错误信息等，让你不切终端也能直接看到 Hermes 正在做什么。

## 功能

### 实时状态显示
读取 Hermes 本地运行状态，展示中文动作文案，例如：
- 正在读取文件
- 正在执行 shell 命令
- 正在修改文件
- 正在打开网页
- 正在等待模型响应
- 正在整理上下文
- 已读取文件 / 已执行 shell 命令 / 已更新任务清单

状态优先使用 `~/.hermes/runtime/live_activity.json` 实时通道，回退到 `~/.hermes/state.db` 会话消息。

### 状态分类与健康感知
- working / thinking / waiting / idle / error
- 长任务保活，避免 terminal command 过早误判完成
- 卡住检测：长时间无进展时提示「疑似卡住」
- cron 超时检测
- 紫灯 waiting 优先显示下一条自动任务和下次时间

### 自动任务与可观测性
- 读取 `~/.hermes/cron/jobs.json`
- 显示任务名、下次运行、最近结果、错误
- 支持右键菜单暂停 / 恢复 / 立即触发

### 桌面交互
- 顶部灵动岛悬浮窗
- 自动收拢为圆球，并支持 hover 恢复
- 最近动作面板
- 最近消息面板
- 性能统计面板
- 系统托盘菜单
- 深色 / 浅色主题
- 自定义状态颜色
- 文案翻译设置
- macOS 桌面通知

## 环境要求

- macOS
- Python 3
- PyQt5
- pyobjc
- psutil
- 本机已安装并运行过 Hermes Agent

## 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 启动

```bash
python3 hermes_pet_v3.py
```

## 打包成 macOS App

仓库已包含：
- `HermesPet.spec`
- `hermes_pet.icns`

使用 PyInstaller：

```bash
pip install pyinstaller
pyinstaller -y HermesPet.spec
```

产物位置：

```bash
dist/HermesPet.app
```

## 主要文件

- `hermes_pet_v3.py`：启动入口
- `ui.py`：主界面与交互逻辑
- `monitor.py`：状态监控、文案归一化、cron 选择
- `config.py`：主题、状态文案、工具映射配置
- `HermesPet.spec`：PyInstaller 打包配置
- `hermes_pet.icns`：应用图标
- `requirements.txt`：依赖列表

## 说明

这个工具优先保证：
1. 状态检测准确
2. 文案表达清楚
3. 自动任务可观测
4. 桌面交互稳定

## License

MIT
