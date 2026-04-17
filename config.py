#!/usr/bin/env python3
"""
Hermes Dynamic Island v3.4 - 赫尔墨斯灵动岛
修复版：字体颜色、智能缩进、数据库查询
"""

import sys
import os
import json
import re
import time
import subprocess
import sqlite3
from ctypes import c_void_p
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse

from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QGraphicsOpacityEffect, QMenu, QAction, QSystemTrayIcon,
    QLineEdit, QPushButton, QSizePolicy, QFrame, QScrollArea,
    QSlider, QColorDialog, QDialog, QListWidget, QListWidgetItem,
    QTabWidget, QGroupBox, QFormLayout, QSpinBox, QComboBox
)
from PyQt5.QtCore import (
    Qt, QTimer, QPoint, QSize, QRect, QRectF, QPropertyAnimation,
    QParallelAnimationGroup, QSequentialAnimationGroup, QPauseAnimation,
    QEasingCurve, pyqtSignal, QThread, pyqtProperty, QEvent,
    QAbstractNativeEventFilter
)
from PyQt5.QtGui import (
    QPainter, QColor, QFont, QCursor, QIcon, QPixmap,
    QPainterPath, QPen, QFontMetrics, QMouseEvent, QKeySequence
)

# macOS 集成
try:
    import objc
    from AppKit import (
        NSFloatingWindowLevel,
        NSWindowCollectionBehaviorCanJoinAllSpaces,
        NSWindowCollectionBehaviorFullScreenAuxiliary,
        NSWindowCollectionBehaviorStationary,
        NSUserNotification,
        NSUserNotificationCenter,
    )
except ImportError:
    objc = None
    NSFloatingWindowLevel = None
    NSWindowCollectionBehaviorCanJoinAllSpaces = None
    NSWindowCollectionBehaviorFullScreenAuxiliary = None
    NSWindowCollectionBehaviorStationary = None

# 音效支持
try:
    from Foundation import NSURL
    from AppKit import NSSound
    SOUND_AVAILABLE = True
except ImportError:
    SOUND_AVAILABLE = False


# ============================================================
# 主题配置 - 修复字体颜色
# ============================================================
class Theme(Enum):
    DARK = "dark"
    LIGHT = "light"

@dataclass
class ThemeConfig:
    bg_color: str
    text_color: str
    text_secondary: str
    border_color: str
    accent_color: str
    input_bg: str
    input_text: str

THEMES = {
    Theme.DARK: ThemeConfig(
        bg_color="rgba(16, 16, 20, 235)",
        text_color="rgba(255, 255, 255, 238)",  # 白色字体
        text_secondary="rgba(255, 255, 255, 145)",
        border_color="rgba(255, 255, 255, 28)",
        accent_color="#30D158",
        input_bg="rgba(30, 30, 35, 220)",
        input_text="rgba(255, 255, 255, 238)"  # 输入框白色字体
    ),
    Theme.LIGHT: ThemeConfig(
        bg_color="rgba(255, 255, 255, 245)",
        text_color="rgba(0, 0, 0, 220)",
        text_secondary="rgba(0, 0, 0, 140)",
        border_color="rgba(0, 0, 0, 20)",
        accent_color="#007AFF",
        input_bg="rgba(240, 240, 240, 220)",
        input_text="rgba(0, 0, 0, 220)"
    )
}

# 状态颜色配置
DEFAULT_STATUS_COLORS = {
    "idle": "#8E8E93",
    "thinking": "#FF9F0A",
    "working": "#30D158",
    "waiting": "#5E5CE6",
    "error": "#FF453A",
    "success": "#64D2FF",
}

# 预设快捷消息
QUICK_MESSAGES = [
    "状态如何？",
    "重启网关",
    "查看最近的错误",
    "当前会话信息",
    "清理旧日志",
    "测试连接",
]

DEFAULT_AGENT_SELECTION = "__global_cli__"
DEFAULT_AGENT_LABEL = "全局最近 CLI 会话"
DEFAULT_SESSION_AUTO = "__auto_latest__"
DEFAULT_SESSION_MODE = "auto"

LIVE_ACTIVITY_SUBSTRING_LABELS = [
    ("waiting for non-streaming", "正在等待模型响应"),
    ("waiting for api response", "正在等待模型响应"),
    ("waiting for provider response", "正在等待模型响应"),
    ("waiting for stream response", "正在等待模型响应"),
    ("waiting for system response", "正在等待系统响应"),
    ("receiving stream response", "正在接收模型响应"),
    ("stale stream detected", "正在重连模型响应流"),
    ("stream retry", "正在重连模型响应流"),
    ("tools concurrently", "正在并发执行工具"),
    ("tool concurrently", "正在并发执行工具"),
]

LOW_INFORMATION_STATUS_TEXTS = {
    "正在执行",
    "正在请求模型响应",
    "正在等待模型响应",
    "正在接收模型响应",
    "模型响应已完成",
    "模型响应异常，正在重试",
    "正在重连模型响应流",
    "正在并发执行工具",
}

TOOL_ACTION_LABELS = {
    "terminal": ("正在执行 shell 命令", "已执行 shell 命令"),
    "shell": ("正在执行 shell 命令", "已执行 shell 命令"),
    "read_file": ("正在读取文件", "已读取文件"),
    "read": ("正在读取文件", "已读取文件"),
    "write_file": ("正在写入文件", "已写入文件"),
    "write": ("正在写入文件", "已写入文件"),
    "patch": ("正在修改文件", "已修改文件"),
    "edit": ("正在修改文件", "已修改文件"),
    "search_files": ("正在检索内容", "已完成内容检索"),
    "grep": ("正在检索内容", "已完成内容检索"),
    "browser_navigate": ("正在打开网页", "已打开网页"),
    "navigate": ("正在打开网页", "已打开网页"),
    "delegate_task": ("正在派发子任务", "已派发子任务"),
    "skill_view": ("正在读取技能", "已读取技能"),
    "todo": ("正在更新任务清单", "已更新任务清单"),
    "execute_code": ("正在执行代码", "已执行代码"),
    "hermes": ("正在调用 Hermes", "已调用 Hermes"),
    "clarify": ("正在等待用户确认", "已确认"),
}

TOOL_SUMMARY_LABELS = {
    "skill": "读取技能",
    "plan": "更新任务清单",
    "session_search": "检索历史会话",
    "delegate_task": "派发子任务",
    "memory": "处理记忆",
    "read": "读取文件",
    "grep": "检索内容",
    "shell": "执行 shell 命令",
    "write": "写入文件",
    "edit": "修改文件",
    "navigate": "打开网页",
    "snapshot": "抓取快照",
    "search": "搜索内容",
    "skill_manage": "更新技能",
    "skill_view": "读取技能",
    "todo": "更新任务清单",
    "read_file": "读取文件",
    "search_files": "检索内容",
    "write_file": "写入文件",
    "patch": "修改文件",
    "browser_navigate": "打开网页",
    "browser_click": "点击网页",
    "browser_type": "输入文本",
    "browser_press": "按下按键",
    "browser_scroll": "滚动网页",
    "browser_vision": "分析页面",
    "browser_console": "执行控制台",
    "browser_back": "返回页面",
    "browser_get_images": "提取图片",
    "terminal": "执行 shell 命令",
    "execute_code": "执行代码",
    "hermes": "调用 Hermes",
    "clarify": "等待用户确认",
}

SYSTEM_COMPLETION_LABELS = {
    "User profile updated": "已更新用户资料",
    "Memory updated": "已更新记忆",
    "Memory saved": "已保存记忆",
    "Skill updated": "已更新技能",
    "Skill created": "已创建技能",
    "Skill saved": "已保存技能",
    "正在整理上下文": "已整理上下文",
    "正在压缩上下文": "已压缩上下文",
}

TRANSIENT_COMPLETION_TEXTS = {
    "正在请求模型响应",
    "正在等待模型响应",
    "正在接收模型响应",
    "模型响应已完成",
    "模型响应异常，正在重试",
    "正在重连模型响应流",
}

# ============================================================
# 摘要评分关键词配置 (M8)
# ============================================================
SCORE_KEYWORDS = {
    # 通用关键词 - 适用于所有项目
    'generic': [
        'update', 'fix', 'add', 'remove', 'implement', 'refactor',
        'completed', '完成', '已完成',
        'review diff', 'diff', '复核', '验证', '测试',
        '根因', '排查', '锁定',
        '读取', '找到', '下一步',
        'notes', '记录',
    ],
    # 项目专用关键词 - 聊天股票等特定场景
    'chat_stock': [
        'ROUND-', '本轮', '落档', '归档', '收口',
        '主控', '执行器',
        '修', '补', '还差', '继续',
    ],
}

# ============================================================
# 工具名称 → 标签映射集中管理
# ============================================================
class ToolRegistry:
    """单例模式：集中管理所有工具名称到标签的映射"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        # 从 TOOL_ACTION_LABELS 初始化
        self._action_labels = {}
        for key, val in TOOL_ACTION_LABELS.items():
            if isinstance(val, tuple) and len(val) == 2:
                self._action_labels[key] = val  # (present, past)
            else:
                self._action_labels[key] = (val, val)

        # 从 TOOL_SUMMARY_LABELS 初始化
        self._summary_labels = dict(TOOL_SUMMARY_LABELS)

        # Browser present/past 标签
        self._browser_present = {
            "browser_click": "点击页面元素",
            "browser_type": "输入文本",
            "browser_press": "按下按键",
            "browser_scroll": "滚动页面",
            "browser_console": "执行浏览器控制台表达式",
            "browser_vision": "分析页面视觉内容",
            "browser_get_images": "提取页面图片",
            "browser_back": "返回上一页",
        }
        self._browser_past = {
            "browser_click": "点击了页面元素",
            "browser_type": "输入了文本",
            "browser_press": "按下了按键",
            "browser_scroll": "滚动了页面",
            "browser_console": "执行了浏览器控制台表达式",
            "browser_vision": "分析了页面视觉内容",
            "browser_get_images": "提取了页面图片",
            "browser_back": "返回了上一页",
        }

        # 通用动词映射
        self._verbs = {
            "read": ("读取", "读取完"),
            "grep": ("检索", "检索完"),
            "navigate": ("访问", "访问完"),
            "snapshot": ("截图", "截图完"),
            "shell": ("执行", "执行完"),
            "write": ("写入", "写入完"),
            "edit": ("修改", "修改完"),
            "search": ("搜索", "搜索完"),
            "browser_use": ("操作", "操作完"),
            "browser_cdp": ("操作", "操作完"),
            "browser_c": ("操作", "操作完"),
        }

    def get_action_label(self, tool_key: str):
        """获取工具的动作标签，返回 (present, past) 元组"""
        if tool_key in self._browser_present:
            return (self._browser_present[tool_key], self._browser_past[tool_key])
        return self._action_labels.get(tool_key, (f"正在{tool_key}", f"已完成{tool_key}"))

    def get_summary_label(self, tool_key: str) -> str:
        """获取工具的摘要标签"""
        if tool_key.startswith("browser_") and tool_key in self._browser_present:
            return self._browser_past[tool_key].replace("了", "")
        return self._summary_labels.get(tool_key, tool_key or "工具调用")

    def get_verb_pair(self, tool_key: str) -> tuple:
        """获取通用动词对 (present, past)"""
        return self._verbs.get(tool_key, ("处理", "处理完"))

    def get_browser_label(self, tool_name: str) -> str:
        """获取 browser_* 工具的标签"""
        return self._browser_present.get(tool_name, "操作页面")


# 全局单例实例
tool_registry = ToolRegistry()

# ============================================================
# 未翻译词记录文件
# ============================================================
UNKNOWN_TRANSLATIONS_FILE = str(Path.home() / ".hermes_pet" / "unknown_translations.json")

# ============================================================
# 配置管理器
# ============================================================
