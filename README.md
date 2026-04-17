# Hermes Tool

Hermes Tool 是一个面向 macOS 的桌面悬浮状态岛，用来实时展示 Hermes Agent 的运行状态、当前动作、涉及文件、自动任务和异常信息。

它的目标很简单：**不打开终端，也能知道 Hermes 现在在做什么。**

## 特性

### 实时状态可视化
- 显示 working / thinking / waiting / idle / error 五种状态
- 将 Hermes runtime / session 状态转换为中文动作文案
- 优先读取 `~/.hermes/runtime/live_activity.json`
- 回退到 `~/.hermes/state.db` 会话消息

### 自动任务可观测
- 读取 `~/.hermes/cron/jobs.json`
- 展示任务名、下次执行时间、最近结果和错误
- waiting 状态优先显示“下一条自动任务 / 下次执行时间”
- 支持右键菜单暂停、恢复、立即触发任务

### 桌面交互
- 顶部灵动岛悬浮窗
- 自动收拢为圆球，并支持 hover 恢复
- 最近动作面板
- 最近消息面板
- 性能统计面板
- 系统托盘菜单
- 深色 / 浅色主题
- 自定义状态颜色
- 翻译设置
- macOS 桌面通知

### 稳定性增强
- 长 terminal command 保活，降低误判完成
- 卡住检测与超时提示
- 状态文案归一化，减少原始英文运行态噪音

## 适用场景

适合用于：
- 本机运行 Hermes CLI / gateway / cron
- 希望不切换终端也能观察 Agent 状态
- 需要持续观察自动推进、定时任务、代码修改、浏览器自动化过程

## 环境要求

- macOS
- Python 3
- PyQt5
- pyobjc
- psutil
- 本机已安装并运行过 Hermes Agent

## 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 启动

当前仓库根目录就是可运行版本，直接执行：

```bash
python3 ui.py
```

如需兼容旧入口，也可以执行：

```bash
python3 hermes_pet_v3.py
```

## 打包为 macOS App

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

## 项目结构

- `ui.py`：主界面、动画、交互逻辑
- `monitor.py`：状态监控、文案归一化、cron 任务选择
- `config.py`：主题、状态文案、工具映射配置
- `hermes_pet_v3.py`：兼容入口
- `HermesPet.spec`：PyInstaller 打包配置
- `hermes_pet.icns`：应用图标
- `requirements.txt`：依赖列表

## 设计目标

这个工具优先保证：
1. 状态检测准确
2. 文案表达清楚
3. 自动任务可观测
4. 桌面交互稳定

## License

MIT
