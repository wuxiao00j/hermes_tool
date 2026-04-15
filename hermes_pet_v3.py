#!/usr/bin/env python3
"""
Hermes Dynamic Island v3.1 - 赫尔墨斯灵动岛
修复版：字体颜色、智能缩进、数据库查询
"""

import sys
import os
import json
import re
import time
import subprocess
import sqlite3
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
    ("receiving stream response", "正在接收模型响应"),
    ("stale stream detected", "正在重连模型响应流"),
    ("stream retry", "正在重连模型响应流"),
]

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
# 配置管理器
# ============================================================
class ConfigManager:
    def __init__(self):
        self.config_dir = Path.home() / ".hermes_pet"
        self.config_dir.mkdir(exist_ok=True)
        self.config_file = self.config_dir / "config.json"
        self.history_file = self.config_dir / "message_history.json"
        self.load_config()
    
    def load_config(self):
        self.config = {
            "theme": "dark",
            "status_colors": DEFAULT_STATUS_COLORS.copy(),
            "auto_hide": False,
            "auto_hide_timeout": 10,
            "opacity": 95,
            "hotkey_toggle": "Alt+H",
            "hotkey_chat": "Alt+Space",
            "instance_id": DEFAULT_AGENT_SELECTION,
            "selected_agent": DEFAULT_AGENT_SELECTION,
            "session_mode": DEFAULT_SESSION_MODE,
            "selected_session_id": DEFAULT_SESSION_AUTO,
            "quick_messages": QUICK_MESSAGES.copy(),
            "activity_panel_visible": True,
        }
        
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    saved = json.load(f)
                    self.config.update(saved)
            except Exception:
                pass

        selected_agent = (
            self.config.get("selected_agent")
            or self.config.get("instance_id")
            or DEFAULT_AGENT_SELECTION
        )
        self.config["selected_agent"] = selected_agent
        self.config["instance_id"] = selected_agent
        self.config["session_mode"] = self.config.get("session_mode") or DEFAULT_SESSION_MODE
        self.config["selected_session_id"] = self.config.get("selected_session_id") or DEFAULT_SESSION_AUTO
    
    def save_config(self):
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            print(f"保存配置失败: {e}")
    
    def load_history(self) -> List[Dict]:
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return []
    
    def save_history(self, history: List[Dict]):
        try:
            with open(self.history_file, 'w') as f:
                json.dump(history[-100:], f, indent=2)
        except Exception:
            pass


# ============================================================
# Hermes Status Monitor - 数据库查询版
# ============================================================
class HermesMonitor(QThread):
    status_changed = pyqtSignal(str, str, dict)
    task_completed = pyqtSignal(str)
    history_updated = pyqtSignal(list)
    performance_updated = pyqtSignal(dict)
    
    IDLE = "idle"
    THINKING = "thinking"
    WORKING = "working"
    WAITING = "waiting"
    ERROR = "error"
    GLOBAL_AGENT_OPTION = DEFAULT_AGENT_SELECTION
    GLOBAL_AGENT_LABEL = DEFAULT_AGENT_LABEL
    LEGACY_NULL_AGENT_FALLBACK = "__legacy_null__"
    
    def __init__(
        self,
        instance_id: str = DEFAULT_AGENT_SELECTION,
        session_mode: str = DEFAULT_SESSION_MODE,
        selected_session_id: str = DEFAULT_SESSION_AUTO,
    ):
        super().__init__()
        self.selected_agent = instance_id or self.GLOBAL_AGENT_OPTION
        self.instance_id = self.selected_agent
        self.session_mode = session_mode or DEFAULT_SESSION_MODE
        self.selected_session_id = selected_session_id or DEFAULT_SESSION_AUTO
        self.hermes_dir = Path.home() / ".hermes"
        self.db_path = self.hermes_dir / "state.db"
        self.sessions_dir = self.hermes_dir / "sessions"
        self.cron_dir = self.hermes_dir / "cron"
        self.cron_jobs_path = self.cron_dir / "jobs.json"
        self.runtime_dir = self.hermes_dir / "runtime"
        self.live_activity_path = self.runtime_dir / "live_activity.json"
        self.live_activity_log_path = self.runtime_dir / "live_activity.log.jsonl"
        self.pet_debug_log_path = self.runtime_dir / "pet_status_debug.log"
        self.running = True
        self.last_status = None
        self.last_session_id = None
        self.check_interval = 1.0
        self._last_history_signature = ()
        
        # 性能统计
        self.performance = {
            "api_calls": 0,
            "total_tokens": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0,
            "avg_response_time": 0,
            "last_response_time": 0,
            "token_data_available": False,
        }
        self._last_completion_signature = None
        
    def run(self):
        while self.running:
            try:
                status, detail, metadata = self._check_status()
                
                if self.last_status == self.WORKING and status in [self.WAITING, self.IDLE]:
                    self.task_completed.emit(detail)
                
                self.last_status = status
                self.status_changed.emit(status, detail, metadata)
                
                self.performance_updated.emit(self.performance.copy())
                
            except Exception as e:
                self.status_changed.emit(self.ERROR, str(e), {})
            
            time.sleep(self.check_interval)
    
    def stop(self):
        self.running = False

    def set_selected_agent(self, selected_agent: str):
        self.selected_agent = selected_agent or self.GLOBAL_AGENT_OPTION
        self.instance_id = self.selected_agent

    def set_session_selection(self, session_mode: str, selected_session_id: str):
        self.session_mode = session_mode or DEFAULT_SESSION_MODE
        self.selected_session_id = selected_session_id or DEFAULT_SESSION_AUTO

    def get_status_snapshot(self) -> Tuple[str, str, dict]:
        return self._check_status()
        
    def _update_token_stats(self) -> None:
        conn = None
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            session = conn.execute("""
                SELECT id, message_count, input_tokens, output_tokens, reasoning_tokens
                FROM sessions
                WHERE ended_at IS NULL
                ORDER BY started_at DESC LIMIT 1
            """).fetchone()
            if not session:
                return
            session_dict = dict(session)
            total_tokens = (
                (session_dict.get('input_tokens') or 0)
                + (session_dict.get('output_tokens') or 0)
                + (session_dict.get('reasoning_tokens') or 0)
            )
            if total_tokens > 0:
                self.performance.update({
                    "total_tokens": total_tokens,
                    "input_tokens": session_dict.get('input_tokens', 0) or 0,
                    "output_tokens": session_dict.get('output_tokens', 0) or 0,
                    "reasoning_tokens": session_dict.get('reasoning_tokens', 0) or 0,
                    "message_count": session_dict.get('message_count', 0) or 0,
                    "token_data_available": True,
                })
        except Exception:
            pass
        finally:
            if conn:
                conn.close()

    def _check_status(self) -> Tuple[str, str, dict]:
        metadata = {
            "instance": self.instance_id,
            "selected_agent": self.selected_agent,
            "status_reason": "no_database_state",
            "last_message_age": None,
            "last_message_role": None,
            "last_message_timestamp": None,
            "session_filter_field": None,
            "session_filter_value": None,
            "using_agent_id_filter": False,
            "fallback_to_legacy_null_agent": False,
            "status": self.last_status or self.WAITING,
            "health_level": "unknown",
        }

        # 1. 检查网关状态
        gateway_running, gateway_info = self._check_gateway()
        metadata['gateway'] = gateway_running
        metadata.update(gateway_info)
        metadata.update(self._cron_job_metadata())

        live_activity = self._load_live_activity_metadata()
        if live_activity:
            metadata.update(live_activity)

        if not gateway_running:
            metadata['status_reason'] = 'gateway_offline'
            metadata['health_level'] = 'red'
            return self.IDLE, "Hermes 离线中", metadata

        if live_activity and live_activity.get("live_status") in {self.WORKING, self.THINKING}:
            metadata["status"] = live_activity.get("live_status")
            metadata['status_reason'] = 'runtime_live_activity'
            metadata['health_level'] = 'yellow' if live_activity.get("live_status") == self.WORKING else ('green' if self._healthy_recent_cron_success(metadata) else 'yellow')
            if metadata.get('recent_live_activity'):
                metadata['recent_activity'] = list(metadata.get('recent_live_activity') or []) + list(metadata.get('recent_activity') or [])
            self._update_token_stats()
            return live_activity.get("live_status"), live_activity.get("live_detail") or "处理中", metadata

        # 2. 查询数据库获取最新会话状态
        session_status = self._check_database()
        if session_status:
            merged = {**metadata, **session_status[2]}
            merged["status"] = session_status[0]
            return session_status[0], session_status[1], merged

        metadata["status"] = self.WAITING
        if metadata.get("cron_overdue"):
            metadata['status_reason'] = 'cron_overdue_without_session_activity'
            metadata['health_level'] = 'red'
            next_display = self._safe_iso_display(metadata.get("cron_next_run_at"))
            return self.ERROR, f"定时任务超时 · 预期 {next_display}", metadata
        if metadata.get("cron_configured"):
            metadata['status_reason'] = 'cron_waiting_without_session_activity'
            metadata['health_level'] = 'green' if self._healthy_recent_cron_success(metadata) else 'yellow'
            next_display = self._safe_iso_display(metadata.get("cron_next_run_at"))
            return self.WAITING, f"自动推进待命 · 下次 {next_display}", metadata
        metadata['health_level'] = 'yellow'
        return self.WAITING, "等待指令", metadata
    
    def _check_gateway(self) -> Tuple[bool, dict]:
        """检查网关状态"""
        try:
            # 读取 gateway_state.json
            gateway_file = self.hermes_dir / "gateway_state.json"
            if gateway_file.exists():
                with open(gateway_file, 'r') as f:
                    data = json.load(f)
                    is_running = data.get("gateway_state") == "running"
                    return is_running, {
                        "active_agents": data.get("active_agents", 0),
                        "platforms": data.get("platforms", {})
                    }
            
            # 备用：检查 PID
            result = subprocess.run(
                ["hermes", "gateway", "status"],
                capture_output=True, text=True, timeout=3
            )
            return "running" in result.stdout.lower(), {}
        except Exception:
            return False, {}
    
    def _parse_timestamp(self, value) -> Optional[datetime]:
        """解析数据库中的时间戳，兼容 ISO 字符串与 Unix 时间戳"""
        if value in (None, ""):
            return None

        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, (int, float)):
            try:
                dt = datetime.fromtimestamp(value, tz=timezone.utc)
            except (OSError, OverflowError, ValueError):
                return None
        elif isinstance(value, str):
            text = value.strip()
            if not text:
                return None

            if text.endswith('Z'):
                text = text[:-1] + '+00:00'

            try:
                dt = datetime.fromisoformat(text)
            except ValueError:
                for fmt in (
                    "%Y-%m-%d %H:%M:%S.%f",
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S.%f",
                    "%Y-%m-%dT%H:%M:%S",
                ):
                    try:
                        dt = datetime.strptime(text, fmt)
                        break
                    except ValueError:
                        continue
                else:
                    return None
        else:
            return None

        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)

        return dt

    def _message_age_seconds(self, timestamp_value) -> Optional[float]:
        """计算消息距离当前时间的秒数"""
        parsed = self._parse_timestamp(timestamp_value)
        if not parsed:
            return None
        return max(0.0, (datetime.now() - parsed).total_seconds())

    def _healthy_recent_cron_success(self, metadata: Dict[str, Any]) -> bool:
        if metadata.get("cron_last_status") != 'ok':
            return False
        age = self._message_age_seconds(metadata.get("cron_last_run_at"))
        return age is not None and age <= 600

    def _is_transition_activity(self, activity: str) -> bool:
        text = str(activity or "").strip()
        if not text:
            return True
        return text in {
            "正在接收模型响应",
            "正在等待模型响应",
            "模型响应已完成",
        } or text.startswith("starting API call #")

    def _append_pet_debug_log(self, status: str, detail: str, metadata: Dict[str, Any]) -> None:
        try:
            self.runtime_dir.mkdir(parents=True, exist_ok=True)
            record = {
                "ts": datetime.now().astimezone().isoformat(),
                "status": status,
                "detail": detail,
                "health_level": (metadata or {}).get("health_level"),
                "status_reason": (metadata or {}).get("status_reason"),
                "live_detail": (metadata or {}).get("live_detail"),
                "live_activity": (metadata or {}).get("live_activity"),
                "live_tool": (metadata or {}).get("live_tool"),
                "recent_activity": (metadata or {}).get("recent_activity"),
                "recent_live_activity": (metadata or {}).get("recent_live_activity"),
                "cron_last_status": (metadata or {}).get("cron_last_status"),
                "cron_next_run_at": (metadata or {}).get("cron_next_run_at"),
                "resolved_session_id": (metadata or {}).get("resolved_session_id"),
            }
            with self.pet_debug_log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _load_cron_jobs(self) -> List[Dict[str, Any]]:
        if not self.cron_jobs_path.exists():
            return []
        try:
            payload = json.loads(self.cron_jobs_path.read_text())
        except Exception:
            return []
        jobs = payload.get("jobs") if isinstance(payload, dict) else payload
        return jobs if isinstance(jobs, list) else []

    def _load_live_activity_metadata(self) -> Dict[str, Any]:
        if not self.live_activity_path.exists():
            return {}
        try:
            payload = json.loads(self.live_activity_path.read_text())
        except Exception:
            return {}
        if not isinstance(payload, dict):
            return {}
        recent_live_activity = self._load_recent_live_activity(limit=5)
        chosen_detail = recent_live_activity[-1] if recent_live_activity else ""
        age = self._message_age_seconds(payload.get("timestamp"))
        if age is not None and age > 20:
            return {}
        activity = str(payload.get("activity") or "").strip()
        tool_name = str(payload.get("current_tool") or "").strip()
        tool_args = payload.get("tool_args") if isinstance(payload.get("tool_args"), dict) else {}
        direct_detail = self._humanize_live_tool_name(tool_name, tool_args, activity)
        detail = chosen_detail or direct_detail

        live_status = self.WAITING
        if payload.get("status") == "working" and (age is None or age <= 8):
            live_status = self.WORKING

        return {
            "live_activity": activity,
            "live_detail": detail,
            "live_direct_detail": direct_detail,
            "live_status": live_status,
            "live_tool": tool_name,
            "live_timestamp": payload.get("timestamp"),
            "live_age_seconds": round(age, 1) if age is not None else None,
            "live_result_preview": payload.get("result_preview") or "",
            "recent_live_activity": recent_live_activity,
        }

    def _load_recent_live_activity(self, limit: int = 5) -> List[str]:
        if not self.live_activity_log_path.exists():
            return []
        try:
            lines = self.live_activity_log_path.read_text().splitlines()
        except Exception:
            return []

        meaningful: List[str] = []
        transitional: List[str] = []
        for raw in reversed(lines[-120:]):
            try:
                payload = json.loads(raw)
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            age = self._message_age_seconds(payload.get("timestamp"))
            if age is not None and age > 180:
                continue
            activity = self._humanize_live_tool_name(
                str(payload.get("current_tool") or "").strip(),
                payload.get("tool_args") if isinstance(payload.get("tool_args"), dict) else {},
                str(payload.get("activity") or "").strip(),
            )
            if not activity:
                continue
            target_bucket = transitional if self._is_transition_activity(activity) else meaningful
            if activity not in target_bucket:
                target_bucket.append(activity)
            if len(meaningful) >= limit:
                break

        chosen = meaningful if meaningful else transitional
        chosen = chosen[:limit]
        chosen.reverse()
        return chosen

    def _humanize_live_tool_name(self, tool_name: str, args: Dict[str, Any], activity: str = "") -> str:
        tool = str(tool_name or "").strip()
        raw_activity = str(activity or "").strip()
        lowered_activity = raw_activity.lower()
        completed = False
        if raw_activity.startswith('executing tool: '):
            tool = raw_activity.split(':', 1)[1].strip()
        elif raw_activity.startswith('tool completed:'):
            completed = True
            tool = raw_activity.split(':', 1)[1].strip().split('(', 1)[0].strip()
        if raw_activity.startswith('starting API call #'):
            return '正在请求模型响应'
        for needle, label in LIVE_ACTIVITY_SUBSTRING_LABELS:
            if needle in lowered_activity:
                return label
        if raw_activity.startswith('API call #') and 'completed' in raw_activity:
            return '模型响应已完成'
        if 'API error recovery' in raw_activity:
            return '模型响应异常，正在重试'
        if tool in TOOL_ACTION_LABELS:
            present_label, past_label = TOOL_ACTION_LABELS[tool]
            if tool in ("read_file", "read", "write_file", "write", "patch", "edit"):
                path = args.get("path") if isinstance(args, dict) else None
                noun = Path(str(path)).name if path else ""
                base = past_label if completed else present_label
                return f"{base}: {noun}" if noun else base
            if tool in ("browser_navigate", "navigate"):
                url = args.get("url") if isinstance(args, dict) else None
                target = self._extract_target_from_url(str(url)) if url else None
                base = past_label if completed else present_label
                return f"{base}: {target}" if target else base
            return past_label if completed else present_label
        if completed and tool:
            return f"已完成 {tool}"
        if raw_activity:
            return raw_activity[:64]
        return f"正在执行 {tool}" if tool else "正在处理"

    def _select_relevant_cron_job(self, jobs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not jobs:
            return None
        preferred_names = ["chat-stock-autopilot", "chat-stock-auto-pilot-test"]
        for name in preferred_names:
            for job in jobs:
                if isinstance(job, dict) and job.get("name") == name:
                    return job
        enabled_jobs = [job for job in jobs if isinstance(job, dict) and job.get("enabled", True)]
        pool = enabled_jobs or [job for job in jobs if isinstance(job, dict)]
        if not pool:
            return None
        def score(job: Dict[str, Any]):
            return str(job.get("next_run_at") or job.get("last_run_at") or job.get("created_at") or "")
        return sorted(pool, key=score, reverse=True)[0]

    def _safe_iso_display(self, value) -> str:
        parsed = self._parse_timestamp(value)
        if not parsed:
            return "—"
        return parsed.strftime("%H:%M")

    def _cron_job_metadata(self) -> Dict[str, Any]:
        job = self._select_relevant_cron_job(self._load_cron_jobs())
        if not job:
            return {
                "cron_configured": False,
                "cron_name": None,
                "cron_state": None,
                "cron_enabled": False,
                "cron_last_status": None,
                "cron_last_run_at": None,
                "cron_next_run_at": None,
                "cron_delivery": None,
                "cron_overdue": False,
            }

        next_dt = self._parse_timestamp(job.get("next_run_at"))
        overdue = False
        if next_dt and job.get("state") == "scheduled" and job.get("enabled", True):
            overdue = (datetime.now() - next_dt).total_seconds() > 180

        return {
            "cron_configured": True,
            "cron_name": job.get("name") or job.get("id"),
            "cron_job_id": job.get("id") or job.get("job_id"),
            "cron_state": job.get("state"),
            "cron_enabled": bool(job.get("enabled", True)),
            "cron_last_status": job.get("last_status"),
            "cron_last_run_at": job.get("last_run_at"),
            "cron_next_run_at": job.get("next_run_at"),
            "cron_schedule_display": job.get("schedule_display") or job.get("schedule"),
            "cron_delivery": job.get("deliver"),
            "cron_last_delivery_error": job.get("last_delivery_error"),
            "cron_last_error": job.get("last_error"),
            "cron_overdue": overdue,
        }

    def _extract_content_text(self, content, default: str = "") -> str:
        """提取 content 中文本内容，兼容字符串和多模态 JSON list"""
        if content is None:
            return default

        if isinstance(content, list):
            text_parts = [item.get('text', '') for item in content if isinstance(item, dict) and item.get('type') == 'text']
            return ' '.join(part for part in text_parts if part).strip() or default

        if isinstance(content, str):
            try:
                content_obj = json.loads(content)
                if isinstance(content_obj, list):
                    text_parts = [item.get('text', '') for item in content_obj if isinstance(item, dict) and item.get('type') == 'text']
                    return ' '.join(part for part in text_parts if part).strip() or default
            except (json.JSONDecodeError, TypeError):
                pass
            return content

        return str(content)

    def _parse_content_payload(self, content):
        if isinstance(content, list):
            return content
        if isinstance(content, str):
            text = content.strip()
            if text.startswith('['):
                try:
                    payload = json.loads(text)
                    if isinstance(payload, list):
                        return payload
                except (json.JSONDecodeError, TypeError):
                    return None
        return None

    def _extract_attachments(self, content) -> List[str]:
        attachments = []
        payload = self._parse_content_payload(content)
        if isinstance(payload, list):
            for item in payload:
                if not isinstance(item, dict):
                    continue
                for key in ("path", "file_path", "image_path", "image_url", "url"):
                    value = item.get(key)
                    if isinstance(value, str) and value.strip():
                        attachments.append(value.strip())
        elif isinstance(content, str):
            path_matches = re.findall(r'(/Users/[^\s"\']+|/home/[^\s"\']+|/tmp/[^\s"\']+)', content)
            attachments.extend(path_matches)

        deduped = []
        seen = set()
        for item in attachments:
            if item not in seen:
                seen.add(item)
                deduped.append(item)
        return deduped

    def _summarize_tool_calls(self, tool_calls) -> List[str]:
        if not tool_calls:
            return []
        try:
            calls = json.loads(tool_calls) if isinstance(tool_calls, str) else tool_calls
        except (json.JSONDecodeError, TypeError):
            calls = tool_calls

        names = []
        if isinstance(calls, list):
            for item in calls:
                if isinstance(item, dict):
                    name = item.get('function', {}).get('name') or item.get('name')
                    if name:
                        names.append(str(name))
        return names

    def _parse_json_object(self, value) -> Dict:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text or not text.startswith('{'):
                return {}
            try:
                parsed = json.loads(text)
                return parsed if isinstance(parsed, dict) else {}
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}

    def _parse_tool_calls_payload(self, tool_calls):
        if not tool_calls:
            return []
        try:
            calls = json.loads(tool_calls) if isinstance(tool_calls, str) else tool_calls
        except (json.JSONDecodeError, TypeError):
            return []
        return calls if isinstance(calls, list) else []

    def _parse_tool_arguments(self, raw_args):
        if isinstance(raw_args, dict):
            return raw_args
        if isinstance(raw_args, str):
            text = raw_args.strip()
            if not text:
                return {}
            try:
                parsed = json.loads(text)
                return parsed if isinstance(parsed, dict) else {"raw": text}
            except (json.JSONDecodeError, TypeError):
                return {"raw": text}
        return {}

    def _normalize_tool_name(self, tool_name: Optional[str]) -> str:
        if not tool_name:
            return ""
        aliases = {
            "read_file": "read",
            "view_file": "read",
            "grep_search": "grep",
            "search_files": "grep",
            "snapshot_page": "snapshot",
            "take_snapshot": "snapshot",
            "browser_navigate": "navigate",
            "open_url": "navigate",
            "visit_url": "navigate",
            "browser_click": "browser_click",
            "browser_type": "browser_type",
            "browser_press": "browser_press",
            "browser_scroll": "browser_scroll",
            "browser_console": "browser_console",
            "browser_vision": "browser_vision",
            "browser_get_images": "browser_get_images",
            "browser_back": "browser_back",
            "execute_shell_command": "shell",
            "run_terminal_command": "shell",
            "terminal": "shell",
            "write_file": "write",
            "patch": "edit",
            "apply_patch": "edit",
            "replace_in_file": "edit",
            "web_search": "search",
            "skill_view": "skill",
            "todo": "plan",
            "session_search": "session_search",
            "delegate_task": "delegate_task",
            "memory": "memory",
        }
        return aliases.get(tool_name, tool_name)

    def _shorten_path(self, value: str) -> str:
        path = value.strip()
        if not path:
            return ""
        try:
            p = Path(path)
            name = p.name
            if name:
                return name
            parts = p.parts
            if len(parts) >= 2:
                return "/".join(parts[-2:])
            return path
        except Exception:
            return path

    def _truncate_text(self, text: str, limit: int = 42) -> str:
        text = (text or "").strip().replace("\n", " ")
        if len(text) <= limit:
            return text
        return text[: limit - 1] + "…"

    def _clean_summary_line(self, text: str) -> str:
        line = (text or "").strip()
        line = re.sub(r'^[\-\*\u2022]+\s*', '', line)
        line = re.sub(r'^\d+[\.\)]\s*', '', line)
        line = re.sub(r'^老板，\s*', '', line)
        line = re.sub(r'^一句话结论[:：]\s*', '', line)
        line = re.sub(r'\s+', ' ', line)
        return line.strip()

    def _score_summary_line(self, line: str) -> int:
        text = (line or "").strip()
        if not text:
            return -100

        lowered = text.lower()
        score = 0

        if re.search(r'[\u4e00-\u9fff]', text):
            score += 2
        if len(text) >= 6:
            score += 1

        positive_tokens = {
            "还差": 8,
            "继续": 4,
            "已完成": 8,
            "完成": 4,
            "ROUND-": 6,
            "本轮": 4,
            "修": 3,
            "补": 3,
            "收口": 5,
            "归档": 6,
            "落档": 6,
            "记录": 3,
            "notes": 4,
            "review diff": 5,
            "diff": 3,
            "复核": 5,
            "验证": 5,
            "测试": 4,
            "根因": 5,
            "锁定": 4,
            "排查": 4,
            "读取": 3,
            "找到": 3,
            "下一步": 3,
        }
        for token, weight in positive_tokens.items():
            if token in text or token in lowered:
                score += weight

        negative_exact = {
            "推进了。",
            "收尾。",
            "收尾",
            "继续推进完了。",
            "继续推进完了",
            "Saved.",
        }
        if text in negative_exact:
            score -= 10

        if lowered.startswith("updated skill") or lowered.startswith("updated existing skill"):
            score -= 8
        if text.startswith("[CONTEXT COMPACTION"):
            score -= 12
        if re.fullmatch(r'[A-Za-z0-9_.:/ -]+', text) and "round-" not in lowered and ".md" not in lowered:
            score -= 3

        return score

    def _pick_salient_text_line(self, text: str) -> str:
        if not text:
            return ""

        candidates: List[Tuple[int, int, str]] = []
        for index, raw_line in enumerate((text or "").replace("\r", "\n").splitlines()):
            line = self._clean_summary_line(raw_line)
            if not line:
                continue
            score = self._score_summary_line(line) - min(index, 6)
            candidates.append((score, -index, line))

        if not candidates:
            return ""

        best_score, _, best_line = max(candidates, key=lambda item: (item[0], item[1], len(item[2])))
        if best_score < 2:
            return ""
        return best_line

    def _extract_assistant_progress_summary(self, content_text: str) -> str:
        text = (content_text or "").strip()
        if not text:
            return ""
        lowered = text.lower()
        if "[context compaction" in lowered or "context compression" in lowered or "compressing context" in lowered:
            return "正在整理上下文"
        if text.startswith("{") or text.startswith("[{"):
            return ""
        best_line = self._pick_salient_text_line(text)
        if not best_line:
            return ""
        lowered_best = best_line.lower()
        if "context compaction" in lowered_best or "context compression" in lowered_best or "compressing context" in lowered_best:
            return "正在整理上下文"
        return self._truncate_text(best_line, 56)

    def _summarize_reasoning_text(self, reasoning_text: str) -> str:
        text = (reasoning_text or "").strip()
        if not text:
            return ""

        heading_match = re.search(r'\*\*([^*\n]+)\*\*', text)
        heading = heading_match.group(1).strip() if heading_match else ""
        if not heading:
            heading = next((line.strip(" *#") for line in text.splitlines() if line.strip()), "")
        lowered = heading.lower()

        special_map = [
            ("inspecting files for planning", "检查文件并规划边界"),
            ("updating progress records", "整理进度记录"),
            ("verifying files", "复核文件改动"),
            ("verifying file records", "复核记录文件"),
            ("evaluating task management", "收口会话任务"),
            ("calculating completion percentage", "计算完成度"),
            ("adjusting file reading", "调整文件读取方式"),
            ("inspecting regex usage", "修正正则匹配"),
            ("updating skill management", "整理可复用经验"),
            ("investigating search issues", "排查搜索与断言问题"),
            ("continuing with the task", "继续推进当前任务"),
            ("deciding on prompt updates", "整理提示词与下一步"),
        ]
        for token, label in special_map:
            if token in lowered:
                return f"思考：{label}"

        action_map = [
            ("inspect", "检查"),
            ("read", "读取"),
            ("search", "检索"),
            ("verify", "复核"),
            ("update", "更新"),
            ("plan", "规划"),
            ("repair", "修复"),
            ("adjust", "调整"),
            ("calculate", "计算"),
            ("evaluate", "评估"),
        ]
        object_map = [
            ("file", "文件"),
            ("record", "记录"),
            ("progress", "进度"),
            ("test", "测试"),
            ("task", "任务"),
            ("regex", "正则"),
            ("skill", "经验"),
            ("baseline", "基线"),
            ("prompt", "提示词"),
            ("search", "搜索结果"),
        ]

        actions = [label for token, label in action_map if token in lowered]
        objects = [label for token, label in object_map if token in lowered]
        if actions or objects:
            phrase = "".join(actions[:1] + objects[:2]) or "整理下一步"
            return f"思考：{phrase}"
        return "思考：整理下一步"

    def _extract_tool_payload(self, msg: Dict) -> Dict:
        content_text = self._extract_content_text(msg.get("raw_content", msg.get("content")), "").strip()
        return self._parse_json_object(content_text)

    def _normalize_diff_path(self, raw_path: str) -> str:
        path = (raw_path or "").strip()
        if not path or path == "/dev/null":
            return ""
        path = re.sub(r'^[ab]/+', '/', path)
        path = re.sub(r'^/+Users/', '/Users/', path)
        path = re.sub(r'^/+home/', '/home/', path)
        path = re.sub(r'^/+tmp/', '/tmp/', path)
        return path

    def _diff_file_action(self, filename: str, status: str = "") -> str:
        present = {
            "PROGRESS.md": "正在整理进度文件",
            "IMPLEMENTATION_NOTES.md": "正在整理实现记录",
            "PROJECT_STATE.md": "正在更新项目状态",
            "ROUND_INDEX.md": "正在更新轮次索引",
            "TEST_RESULTS.md": "正在整理测试记录",
            "GATE_RESULTS.md": "正在整理 Gate 结果",
        }
        past = {
            "PROGRESS.md": "已更新进度文件",
            "IMPLEMENTATION_NOTES.md": "已更新实现记录",
            "PROJECT_STATE.md": "已更新项目状态",
            "ROUND_INDEX.md": "已更新轮次索引",
            "TEST_RESULTS.md": "已更新测试记录",
            "GATE_RESULTS.md": "已更新 Gate 结果",
        }
        if re.fullmatch(r'ROUND-\d+\.md', filename or "", re.IGNORECASE):
            return "正在整理单轮归档" if status == self.WORKING else "已更新单轮归档"
        if re.fullmatch(r'ROUND-\d+\.txt', filename or "", re.IGNORECASE):
            return "正在整理本轮提示词" if status == self.WORKING else "已更新本轮提示词"
        mapping = present if status == self.WORKING else past
        return mapping.get(filename or "", "正在复核文件改动" if status == self.WORKING else "已更新文件")

    def _extract_diff_topics(self, diff_text: str) -> Tuple[str, List[str]]:
        added_round_label = ""
        context_round_label = ""
        added_topics: List[str] = []
        context_topics: List[str] = []

        for raw_line in (diff_text or "").splitlines():
            if not raw_line or raw_line.startswith(("+++", "---", "@@")):
                continue
            prefix = raw_line[0]
            if prefix not in ("+", " "):
                continue
            line = raw_line[1:].strip()
            if not line:
                continue

            if re.match(r'#{2,3}\s*ROUND[- ]?\d+', line, re.IGNORECASE):
                if prefix == "+":
                    added_round_label = re.sub(r'^[#\s]+', '', line)
                elif not context_round_label:
                    context_round_label = re.sub(r'^[#\s]+', '', line)
                continue
            if re.match(r'#{2,3}\s*Round\s+\d+', line, re.IGNORECASE):
                if prefix == "+":
                    added_round_label = re.sub(r'^[#\s]+', '', line)
                elif not context_round_label:
                    context_round_label = re.sub(r'^[#\s]+', '', line)
                continue

            target_topics = added_topics if prefix == "+" else context_topics
            if line.startswith("- 目标："):
                target_topics.append("目标")
            elif line.startswith("- 结果："):
                target_topics.append("结果")
            elif line.startswith("- 当前结论："):
                target_topics.append("当前结论")
            elif line.startswith("- 下一步动作："):
                target_topics.append("下一步动作")
            elif line.startswith("## 本轮目标"):
                target_topics.append("本轮目标")
            elif line.startswith("### 本轮短摘要"):
                target_topics.append("本轮短摘要")
            elif line.startswith("### 已完成"):
                target_topics.append("已完成")
            elif line.startswith("## 执行结果"):
                target_topics.append("执行结果")

        deduped: List[str] = []
        seen = set()
        for item in added_topics + context_topics:
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        return added_round_label or context_round_label, deduped[:3]

    def _summarize_diff_payload(self, diff_text: str, status: str = "") -> str:
        if not diff_text:
            return ""

        changed_files: List[str] = []
        for raw_line in diff_text.splitlines():
            if raw_line.startswith("+++ "):
                normalized = self._normalize_diff_path(raw_line[4:].strip())
                if normalized:
                    changed_files.append(normalized)

        filename = self._shorten_path(changed_files[0]) if changed_files else ""
        action = self._diff_file_action(filename, status)
        round_label, topics = self._extract_diff_topics(diff_text)

        summary = f"{action}：{filename}" if filename else action
        extras: List[str] = []
        if round_label:
            extras.append(round_label)
        if topics:
            extras.append(" / ".join(topics))
        if extras:
            summary += " · " + " · ".join(extras)
        return self._truncate_text(summary, 64)

    def _summarize_tool_payload_text(self, msg: Dict, status: str = "") -> str:
        payload = self._extract_tool_payload(msg)
        if not payload:
            return ""

        diff_text = payload.get("diff")
        if isinstance(diff_text, str) and diff_text.strip():
            return self._summarize_diff_payload(diff_text, status)

        output_text = payload.get("output")
        if isinstance(output_text, str) and output_text.strip():
            if "All tests passed!" in output_text:
                return "测试通过：All tests passed!"
            if "No linter for .md files" in output_text:
                return "已跳过 Markdown lint"
            if "RICH=" in output_text:
                return "已读取渲染文本并复核断言"
            if ".dart" in output_text and "loading" in output_text:
                return "已执行测试并复核输出"

        embedded_content = payload.get("content")
        if isinstance(embedded_content, str) and embedded_content.strip():
            if re.search(r'^\s*\d+\|#\s*Progress\b', embedded_content, re.MULTILINE):
                return "已读取进度记录"
            if re.search(r'^\s*\d+\|#\s*Project State\b', embedded_content, re.MULTILINE):
                return "已读取项目状态"
            if re.search(r'^\s*\d+\|#\s*Implementation Notes\b', embedded_content, re.MULTILINE):
                return "已读取实现记录"
            if re.search(r'^\s*\d+\|#\s*ROUND-\d+\b', embedded_content, re.MULTILINE):
                round_match = re.search(r'ROUND-\d+', embedded_content)
                if round_match:
                    return f"已读取单轮记录：{round_match.group(0)}"

        return ""

    def _extract_priority_text_summary(self, msg: Dict, status: str = "") -> str:
        role = msg.get("role", "")
        content_text = self._extract_content_text(msg.get("raw_content", msg.get("content")), "").strip()

        if role == "assistant":
            natural_summary = self._extract_assistant_progress_summary(content_text)
            if natural_summary:
                return natural_summary
            reasoning_summary = self._summarize_reasoning_text(str(msg.get("reasoning") or ""))
            if reasoning_summary:
                return reasoning_summary
            return ""

        if role == "tool":
            return self._summarize_tool_payload_text(msg, status)

        return ""

    def _extract_target_from_url(self, value: str) -> str:
        text = (value or "").strip()
        if not text:
            return ""
        try:
            parsed = urlparse(text)
            if parsed.netloc:
                return parsed.netloc
        except Exception:
            pass
        return self._truncate_text(text, 40)

    def _format_pattern_target(self, value: str, limit: int = 40) -> str:
        text = (value or "").strip().replace("\n", " ")
        if not text:
            return ""
        text = re.sub(r'\s+', ' ', text)
        if len(text) <= limit:
            return text

        rich_match = re.search(r"(richTextContaining\([^)]*\))", text)
        if rich_match:
            snippet = rich_match.group(1)
            prefix = snippet.split(',', 1)[0].strip()
            return self._truncate_text(prefix + "...", limit)

        contains_match = re.search(r"(contains\([^)]*\))", text)
        if contains_match:
            snippet = contains_match.group(1)
            prefix = snippet.split('|', 1)[0].strip()
            return self._truncate_text(prefix + "...", limit)

        paren_match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\((.*)", text)
        if paren_match:
            return self._truncate_text(paren_match.group(1) + "(...)", limit)

        return self._truncate_text(text, limit)

    def _extract_target_from_plan_content(self, content_text: str) -> str:
        payload = self._parse_json_object(content_text)
        if not payload:
            return ""
        summary = payload.get("summary")
        if isinstance(summary, dict):
            total = summary.get("total")
            if isinstance(total, int) and total > 0:
                return f"{total} 个任务"
        todos = payload.get("todos")
        if isinstance(todos, list) and todos:
            return f"{len(todos)} 个任务"
        return ""

    def _extract_target_from_skill_content(self, content_text: str) -> str:
        payload = self._parse_json_object(content_text)
        if isinstance(payload.get("name"), str) and payload.get("name").strip():
            return payload.get("name").strip()
        return ""

    def _tool_priority(self, tool_name: str, args: Dict) -> int:
        priority = {
            "delegate_task": 120,
            "skill": 115,
            "plan": 110,
            "memory": 108,
            "session_search": 106,
            "browser_vision": 104,
            "browser_console": 103,
            "browser_type": 102,
            "browser_click": 101,
            "browser_press": 100,
            "browser_scroll": 99,
            "browser_get_images": 98,
            "browser_back": 97,
            "read": 96,
            "grep": 95,
            "shell": 94,
            "write": 93,
            "edit": 92,
            "navigate": 91,
            "snapshot": 90,
        }
        score = priority.get(tool_name, 10)
        if args:
            score += 1
        return score

    def _extract_best_tool_call(self, msg: Dict) -> Tuple[str, Dict, int]:
        tool_calls = self._parse_tool_calls_payload(msg.get("tool_calls"))
        if not tool_calls:
            return self._normalize_tool_name(str(msg.get("tool_name") or "")), {}, 0

        best_name = ""
        best_args: Dict = {}
        best_score = -1
        for item in tool_calls:
            if not isinstance(item, dict):
                continue
            function = item.get("function") if isinstance(item.get("function"), dict) else {}
            raw_name = function.get("name") or item.get("name") or ""
            tool_name = self._normalize_tool_name(str(raw_name) if raw_name else "")
            args = self._parse_tool_arguments(
                function.get("arguments") if isinstance(function, dict) else item.get("arguments")
            )
            score = self._tool_priority(tool_name, args)
            if score > best_score:
                best_name = tool_name
                best_args = args
                best_score = score
        return best_name, best_args, len(tool_calls)

    def _browser_action_label(self, tool_name: str) -> str:
        labels = {
            "browser_click": "点击页面元素",
            "browser_type": "输入文本",
            "browser_press": "按下按键",
            "browser_scroll": "滚动页面",
            "browser_console": "执行浏览器控制台表达式",
            "browser_vision": "分析页面视觉内容",
            "browser_get_images": "提取页面图片",
            "browser_back": "返回上一页",
        }
        return labels.get(tool_name, "操作页面")

    def _compose_tool_summary(self, tool_name: str, target: str, error_state: bool = False, call_count: int = 1) -> str:
        prefix = "❌" if error_state else self._tool_emoji(tool_name)
        if tool_name.startswith("browser_"):
            label = self._browser_action_label(tool_name)
            summary = f"{prefix} {label}"
            if target:
                summary += f" {target}"
        else:
            label = TOOL_SUMMARY_LABELS.get(tool_name, tool_name or "工具调用")
            summary = f"{prefix} {label}"
            if target:
                summary += f" {target}"
        if call_count > 1:
            summary += f" +{call_count - 1}"
        if error_state:
            summary += " [异常]"
        return summary

    def _extract_activity_descriptor(self, msg: Dict) -> Tuple[str, str]:
        tool_name, tool_args = self._extract_primary_tool(msg)
        target = self._extract_tool_target(tool_name, tool_args, msg)
        return tool_name, target

    def _extract_target_from_activity(self, activity: str, tool_name: str) -> str:
        text = self._activity_core(activity)
        if not text:
            return ""
        prefix_map = {
            "skill": ["📚 skill", "skill", "正在调用 skill:", "刚完成 skill:"],
            "plan": ["📋 plan", "📋 计划", "正在规划", "刚完成计划"],
            "read": ["📖 read", "正在读取", "刚读取完"],
            "grep": ["🔎 grep", "正在检索", "刚检索"],
            "session_search": ["🔍 检索历史会话：", "正在检索历史会话：", "刚检索历史会话："],
            "delegate_task": ["🧩 派发子任务：", "正在派发子任务：", "刚派发子任务："],
            "memory": ["🧠 保存记忆", "🧠 更新记忆", "🧠 替换记忆", "正在保存记忆", "正在更新记忆", "正在替换记忆", "刚保存记忆", "刚更新记忆", "刚替换记忆"],
            "browser_click": ["🖱 点击页面元素", "正在点击页面元素", "刚点击页面元素"],
            "browser_type": ["⌨️ 输入文本", "正在输入文本", "刚输入文本"],
            "browser_press": ["⌨️ 按下按键", "正在按下按键", "刚按下按键"],
            "browser_scroll": ["↕️ 向下滚动", "↕️ 向上滚动", "正在向下滚动", "正在向上滚动", "刚向下滚动", "刚向上滚动", "↕️ 滚动页面", "正在滚动页面", "刚滚动页面"],
            "browser_console": ["🧪 执行浏览器控制台表达式", "正在执行浏览器控制台表达式", "刚执行浏览器控制台表达式"],
            "browser_vision": ["👁 分析页面视觉内容", "正在分析页面视觉内容", "刚分析页面视觉内容"],
            "browser_get_images": ["🖼 提取页面图片", "正在提取页面图片", "刚提取页面图片"],
            "browser_back": ["↩️ 返回上一页", "正在返回上一页", "刚返回上一页"],
        }
        for prefix in prefix_map.get(tool_name, []):
            if text.startswith(prefix):
                remainder = text[len(prefix):].strip(" ：:")
                return remainder
        return ""

    def _extract_primary_tool(self, msg: Dict) -> Tuple[str, Dict]:
        tool_name, tool_args, _ = self._extract_best_tool_call(msg)
        if tool_name:
            return tool_name, tool_args

        if msg.get("role") == "tool":
            content_text = self._extract_content_text(msg.get("raw_content", msg.get("content")), "").strip()
            payload = self._parse_json_object(content_text)
            if isinstance(payload.get("name"), str) and payload.get("name").strip() and payload.get("description"):
                return "skill", payload
            if isinstance(payload.get("summary"), dict) or isinstance(payload.get("todos"), list):
                return "plan", payload

        return self._normalize_tool_name(str(msg.get("tool_name") or "")), {}

    def _extract_tool_target(self, tool_name: str, args: Dict, msg: Dict) -> str:
        content_text = self._extract_content_text(msg.get("raw_content", msg.get("content")), "").strip()
        attachments = msg.get("attachments") or []
        if attachments and tool_name not in {"skill", "plan", "browser_vision"}:
            first = attachments[0]
            if isinstance(first, str):
                return self._shorten_path(first)

        if tool_name == "skill":
            for key in ("name", "skill", "skill_name"):
                value = args.get(key)
                if isinstance(value, str) and value.strip():
                    return self._truncate_text(value.strip(), 44)
            return self._extract_target_from_skill_content(content_text)

        if tool_name == "plan":
            target = self._extract_target_from_plan_content(content_text)
            if target:
                return target
            todos = args.get("todos")
            if isinstance(todos, list) and todos:
                return f"{len(todos)} task(s)"

        if tool_name == "session_search":
            for key in ("query", "q", "search"):
                value = args.get(key)
                if isinstance(value, str) and value.strip():
                    return self._truncate_text(value.strip(), 40)
            return "最近会话"

        if tool_name == "delegate_task":
            for key in ("title", "task_title", "description", "task", "prompt", "summary"):
                value = args.get(key)
                if isinstance(value, str) and value.strip():
                    return self._truncate_text(value.strip(), 40)
            agent = args.get("agent") or args.get("agent_id") or args.get("target_agent")
            if isinstance(agent, str) and agent.strip():
                return self._truncate_text(f"给 {agent.strip()}", 40)
            return "子任务"

        if tool_name == "memory":
            action = str(args.get("action") or "").strip().lower()
            target = str(args.get("target") or "").strip()
            action_map = {
                "save": "保存记忆",
                "create": "保存记忆",
                "update": "更新记忆",
                "replace": "替换记忆",
            }
            label = action_map.get(action, "处理记忆")
            return f"{label}{(' ' + target) if target else ''}".strip()

        if tool_name == "browser_click":
            ref = args.get("ref")
            if isinstance(ref, str) and ref.strip():
                return ref.strip()
            return "页面元素"

        if tool_name == "browser_type":
            ref = str(args.get("ref") or "").strip()
            text = str(args.get("text") or "").strip()
            if ref and text:
                return self._truncate_text(f"{ref}: {text}", 40)
            if ref:
                return ref
            if text:
                return self._truncate_text(text, 32)
            return "输入框"

        if tool_name == "browser_press":
            key = args.get("key")
            if isinstance(key, str) and key.strip():
                return key.strip()
            return "按键"

        if tool_name == "browser_scroll":
            direction = args.get("direction")
            if isinstance(direction, str) and direction.strip():
                return "向下" if direction.strip().lower() == "down" else "向上" if direction.strip().lower() == "up" else direction.strip()
            return "页面"

        if tool_name == "browser_console":
            expr = args.get("expression")
            if isinstance(expr, str) and expr.strip():
                return self._truncate_text(expr.strip(), 40)
            return "控制台"

        if tool_name == "browser_vision":
            question = args.get("question")
            if isinstance(question, str) and question.strip():
                return self._truncate_text(question.strip(), 40)
            return "页面"

        if tool_name == "browser_get_images":
            return "页面"

        if tool_name == "browser_back":
            return ""

        if tool_name in {"read", "write", "edit"}:
            for key in ("path", "file_path", "filename", "target_file"):
                value = args.get(key)
                if isinstance(value, str) and value.strip():
                    return self._shorten_path(value)

        if tool_name == "grep":
            for key in ("pattern", "query", "regex", "search", "needle"):
                value = args.get(key)
                if isinstance(value, str) and value.strip():
                    return self._format_pattern_target(value, 42)

        if tool_name in {"navigate", "browser_use", "browser_cdp", "browser_c"}:
            for key in ("url", "href", "target", "page_url"):
                value = args.get(key)
                if isinstance(value, str) and value.strip():
                    return self._extract_target_from_url(value)
            action = args.get("action")
            if isinstance(action, str) and action.strip():
                return self._truncate_text(action, 28)

        if tool_name == "snapshot":
            for key in ("target", "mode", "name", "filename"):
                value = args.get(key)
                if isinstance(value, str) and value.strip():
                    return self._truncate_text(value, 24)
            if "full" in content_text.lower():
                return "full"

        if tool_name == "shell":
            for key in ("command", "cmd", "shell_command", "raw"):
                value = args.get(key)
                if isinstance(value, str) and value.strip():
                    return self._truncate_text(value, 38)

        if tool_name == "search":
            for key in ("query", "search", "q"):
                value = args.get(key)
                if isinstance(value, str) and value.strip():
                    return self._truncate_text(value, 36)

        if tool_name:
            match = re.search(r'([A-Za-z0-9_/.-]+\.[A-Za-z0-9]+)', content_text)
            if match:
                return self._shorten_path(match.group(1))

        return ""

    def _message_has_error(self, msg: Dict) -> bool:
        haystacks = [
            str(msg.get("raw_content") or ""),
            str(msg.get("content") or ""),
            str(msg.get("reasoning") or ""),
        ]
        lowered = " ".join(haystacks).lower()
        return any(token in lowered for token in ("[error]", " error", "failed", "stderr", "traceback", "exception"))

    def _activity_core(self, activity: str) -> str:
        text = (activity or "").strip()
        if not text:
            return ""
        return re.sub(r'^[^\w\u4e00-\u9fff]+', '', text).strip()

    def _top_detail_from_activity(self, msg: Dict, status: str) -> str:
        activity = self._activity_core(msg.get("activity", ""))
        role = msg.get("role", "")
        if not activity:
            return ""

        if activity.startswith("上传/提问:"):
            return activity.replace("上传/提问:", "上传图片:", 1)

        if activity.startswith("用户输入:"):
            return "已发送，等待 Hermes 响应..."

        if activity.startswith("❌"):
            return self._truncate_text(activity, 48)

        priority_summary = self._extract_priority_text_summary(msg, status)
        if priority_summary:
            return self._truncate_text(priority_summary, 48)

        if activity.startswith("模型回复:"):
            text = activity.replace("模型回复:", "", 1).strip()
            return self._truncate_text(text or "Hermes 已回复", 48)

        tool_name, target = self._extract_activity_descriptor(msg)
        if not target and tool_name:
            target = self._extract_target_from_activity(activity, tool_name)
        tool_name, _, call_count = self._extract_best_tool_call(msg)

        if tool_name == "skill":
            summary = f"正在调用 skill: {target}" if status == self.WORKING else f"刚完成 skill: {target}"
            if call_count > 1:
                summary += f" +{call_count - 1}"
            return self._truncate_text(summary.strip(), 48)

        if tool_name == "plan":
            summary = f"正在规划 {target}" if status == self.WORKING else f"刚完成计划 {target}"
            if call_count > 1:
                summary += f" +{call_count - 1}"
            return self._truncate_text(summary.strip(), 48)

        if tool_name == "session_search":
            summary = f"正在检索历史会话：{target}" if status == self.WORKING else f"刚检索历史会话：{target}"
            if call_count > 1:
                summary += f" +{call_count - 1}"
            return self._truncate_text(summary.strip(), 48)

        if tool_name == "delegate_task":
            summary = f"正在派发子任务：{target}" if status == self.WORKING else f"刚派发子任务：{target}"
            if call_count > 1:
                summary += f" +{call_count - 1}"
            return self._truncate_text(summary.strip(), 48)

        if tool_name == "memory":
            base = target or "处理记忆"
            summary = f"正在{base}" if status == self.WORKING else f"刚{base}"
            if call_count > 1:
                summary += f" +{call_count - 1}"
            return self._truncate_text(summary.strip(), 48)

        browser_present = {
            "browser_click": "点击页面元素",
            "browser_type": "输入文本",
            "browser_press": "按下按键",
            "browser_scroll": "滚动页面",
            "browser_console": "执行浏览器控制台表达式",
            "browser_vision": "分析页面视觉内容",
            "browser_get_images": "提取页面图片",
            "browser_back": "返回上一页",
        }
        browser_past = {
            "browser_click": "点击了页面元素",
            "browser_type": "输入了文本",
            "browser_press": "按下了按键",
            "browser_scroll": "滚动了页面",
            "browser_console": "执行了浏览器控制台表达式",
            "browser_vision": "分析了页面视觉内容",
            "browser_get_images": "提取了页面图片",
            "browser_back": "返回了上一页",
        }
        if tool_name in browser_present:
            action = browser_present[tool_name] if status == self.WORKING else browser_past[tool_name]
            summary = f"正在{action}" if status == self.WORKING else f"刚{action}"
            if target:
                summary += f" {target}"
            if call_count > 1:
                summary += f" +{call_count - 1}"
            return self._truncate_text(summary.strip(), 48)

        verbs = {
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
        present, past = verbs.get(tool_name, ("处理", "处理完"))

        if status == self.WORKING:
            summary = f"正在{present}{(' ' + target) if target else ''}"
            if call_count > 1:
                summary += f" +{call_count - 1}"
            return self._truncate_text(summary, 48)
        if role == "tool":
            summary = f"刚{past}{(' ' + target) if target else ''}"
            if call_count > 1:
                summary += f" +{call_count - 1}"
            return self._truncate_text(summary, 48)
        return self._truncate_text(activity, 48)

    def _build_activity_summary(self, msg: Dict) -> str:
        role = msg.get("role", "")
        tool_name, tool_args = self._extract_primary_tool(msg)
        _, _, call_count = self._extract_best_tool_call(msg)
        tool_names = self._summarize_tool_calls(msg.get("tool_calls"))
        content_text = self._extract_content_text(msg.get("raw_content", msg.get("content")), "").strip().replace("\n", " ")
        attachments = msg.get("attachments") or []
        error_state = self._message_has_error(msg)

        if role == "user":
            if attachments:
                names = ", ".join(Path(item).name or item for item in attachments[:2])
                return f"上传/提问: {names}"
            return f"用户输入: {content_text[:80] or '新消息'}"

        priority_summary = self._extract_priority_text_summary(msg)
        if priority_summary:
            return self._truncate_text(priority_summary, 56)

        if role == "assistant" and tool_names:
            target = self._extract_tool_target(tool_name, tool_args, msg)
            summary = self._compose_tool_summary(tool_name, target, error_state, call_count)
            return self._truncate_text(summary, 56)

        if role == "assistant":
            return f"模型回复: {self._truncate_text(content_text or '已回复', 42)}"

        if role == "tool":
            target = self._extract_tool_target(tool_name, tool_args, msg)
            summary = self._compose_tool_summary(tool_name, target, error_state, call_count)
            return self._truncate_text(summary, 56)

        return content_text[:80] or "最近活动"

    def _tool_emoji(self, tool_name: str) -> str:
        mapping = {
            "skill": "📚",
            "plan": "📋",
            "read": "📖",
            "grep": "🔎",
            "navigate": "🌐",
            "snapshot": "📸",
            "shell": "⌨️",
            "write": "📝",
            "edit": "🛠",
            "search": "🔍",
            "session_search": "🔍",
            "delegate_task": "🧩",
            "memory": "🧠",
            "browser_click": "🖱",
            "browser_type": "⌨️",
            "browser_press": "⌨️",
            "browser_scroll": "↕️",
            "browser_console": "🧪",
            "browser_vision": "👁",
            "browser_get_images": "🖼",
            "browser_back": "↩️",
            "browser_use": "🌐",
            "browser_cdp": "🌐",
            "browser_c": "🌐",
        }
        return mapping.get(tool_name, "🔧")

    def _enrich_message(self, msg) -> Dict:
        msg_dict = dict(msg) if not isinstance(msg, dict) else msg.copy()
        msg_dict.setdefault("tool_name", None)
        msg_dict.setdefault("tool_calls", None)
        msg_dict.setdefault("tool_call_id", None)
        msg_dict.setdefault("timestamp", None)
        msg_dict.setdefault("reasoning", None)
        msg_dict.setdefault("finish_reason", None)
        msg_dict.setdefault("token_count", None)
        raw_content = msg_dict.get("content")
        attachments = self._extract_attachments(raw_content)
        msg_dict["raw_content"] = raw_content
        msg_dict["attachments"] = attachments
        msg_dict["content"] = self._extract_content_text(raw_content, '[多模态内容]')
        msg_dict["activity"] = self._build_activity_summary(msg_dict)
        return msg_dict

    def _message_signature(self, msg: Dict, index: int = 0) -> str:
        return "|".join([
            str(msg.get("timestamp") or ""),
            str(msg.get("role") or ""),
            str(msg.get("tool_name") or ""),
            str(msg.get("tool_call_id") or ""),
            str(index),
            (msg.get("content") or "")[:80],
        ])

    def _emit_history_if_changed(self, history: List[Dict]):
        signature = tuple(self._message_signature(msg, idx) for idx, msg in enumerate(history))
        if signature != self._last_history_signature:
            self._last_history_signature = signature
            self.history_updated.emit(history)

    def _session_file_path(self, session_id: str) -> Path:
        return self.sessions_dir / f"session_{session_id}.json"

    def _list_live_cli_sessions(self, limit: int = 12) -> List[Dict]:
        candidates: List[Dict] = []
        try:
            for session_file in self.sessions_dir.glob("session_*.json"):
                try:
                    payload = json.loads(session_file.read_text())
                except Exception:
                    continue
                if payload.get("platform") != "cli":
                    continue
                session_id = payload.get("session_id") or session_file.stem.replace("session_", "", 1)
                if not session_id:
                    continue
                messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []
                last_msg = messages[-1] if messages else {}
                last_updated = payload.get("last_updated")
                last_dt = self._parse_timestamp(last_updated)
                last_ts = last_dt.timestamp() if last_dt else session_file.stat().st_mtime
                candidates.append({
                    "id": session_id,
                    "source": "cli",
                    "started_at": payload.get("session_start"),
                    "message_count": len(messages),
                    "last_active": last_ts,
                    "last_updated": last_updated,
                    "last_role": last_msg.get("role"),
                    "last_content": self._extract_content_text(last_msg.get("content"), ""),
                    "last_tool_name": last_msg.get("tool_name"),
                    "last_tool_calls": last_msg.get("tool_calls"),
                    "last_reasoning": last_msg.get("reasoning"),
                    "session_json_exists": True,
                    "selection_source": "live_session_json",
                })
        except Exception:
            return []

        candidates.sort(key=lambda item: item.get("last_active") or 0, reverse=True)
        return candidates[:limit]

    def _prefer_live_session_candidate(self, db_sessions: List[Dict], live_sessions: List[Dict], metadata: Dict) -> Tuple[Optional[Dict], Dict]:
        db_by_id = {str(item.get("id")): item for item in db_sessions}
        selected_manual_id = self.selected_session_id if self.session_mode == "manual" and self.selected_session_id not in ("", DEFAULT_SESSION_AUTO) else None

        if selected_manual_id:
            if selected_manual_id in db_by_id:
                chosen = db_by_id[selected_manual_id]
                metadata.update({
                    "resolved_session_id": chosen["id"],
                    "session_selection_reason": "manual_db_session",
                    "session_json_exists": self._session_file_path(chosen["id"]).exists(),
                    "session_exists_in_db": True,
                })
                return chosen, metadata
            for live in live_sessions:
                if live["id"] == selected_manual_id:
                    metadata.update({
                        "resolved_session_id": live["id"],
                        "session_selection_reason": "manual_live_session_json",
                        "session_json_exists": True,
                        "session_exists_in_db": False,
                        "live_session_last_updated": live.get("last_updated"),
                    })
                    return live, metadata
            metadata["session_fallback_reason"] = "manual_session_missing"

        freshest_live = live_sessions[0] if live_sessions else None
        freshest_db = db_sessions[0] if db_sessions else None

        if freshest_live and freshest_db:
            live_last = freshest_live.get("last_active") or 0
            db_last = freshest_db.get("last_active") or 0
            if freshest_live["id"] not in db_by_id and live_last >= db_last:
                metadata.update({
                    "resolved_session_id": freshest_live["id"],
                    "session_selection_reason": "live_session_json_newer_than_db",
                    "session_json_exists": True,
                    "session_exists_in_db": False,
                    "live_session_last_updated": freshest_live.get("last_updated"),
                    "db_latest_session_id": freshest_db.get("id"),
                    "db_latest_last_active": db_last,
                })
                return freshest_live, metadata

        if freshest_db:
            metadata.update({
                "resolved_session_id": freshest_db["id"],
                "session_selection_reason": "database_recent_session",
                "session_json_exists": self._session_file_path(freshest_db["id"]).exists(),
                "session_exists_in_db": True,
            })
            return freshest_db, metadata

        if freshest_live:
            metadata.update({
                "resolved_session_id": freshest_live["id"],
                "session_selection_reason": "live_session_json_only",
                "session_json_exists": True,
                "session_exists_in_db": False,
                "live_session_last_updated": freshest_live.get("last_updated"),
            })
            return freshest_live, metadata

        return None, metadata

    def _load_live_session_messages(self, session_id: str, fallback_history: List[Dict]) -> Tuple[List[Dict], Optional[str]]:
        session_file = self._session_file_path(session_id)
        if not session_file.exists():
            return fallback_history, None

        try:
            payload = json.loads(session_file.read_text())
        except Exception:
            return fallback_history, None

        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages:
            return fallback_history, payload.get("last_updated")

        live_messages: List[Dict] = []
        last_updated = payload.get("last_updated")
        for index, item in enumerate(messages[-10:]):
            if not isinstance(item, dict):
                continue
            msg = item.copy()
            if not msg.get("timestamp"):
                msg["timestamp"] = last_updated if index == len(messages[-10:]) - 1 else None
            live_messages.append(self._enrich_message(msg))

        return live_messages or fallback_history, last_updated

    def _has_session_column(self, conn, column_name: str) -> bool:
        return column_name in set(self._get_session_columns(conn))

    def _fetch_recent_messages(self, conn, session_id: str, limit: int = 8) -> List[Dict]:
        rows = conn.execute("""
            SELECT role, content, tool_name, tool_calls, timestamp, reasoning, finish_reason, token_count
            FROM messages
            WHERE session_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (session_id, limit)).fetchall()
        return [self._enrich_message(row) for row in reversed(rows)]

    def _query_recent_cli_session(self, conn, where_sql: str, params: List[str], prefer_agent: Optional[str] = None) -> Optional[sqlite3.Row]:
        order_prefix = ""
        order_params: List[str] = []
        if prefer_agent is not None:
            order_prefix = "CASE WHEN s.agent_id = ? THEN 0 ELSE 1 END, "
            order_params.append(prefer_agent)

        query_params = params + order_params
        session = conn.execute(f"""
            SELECT s.*
            FROM sessions s
            JOIN (
                SELECT session_id, MAX(timestamp) AS last_ts
                FROM messages
                GROUP BY session_id
            ) m ON s.id = m.session_id
            WHERE {where_sql}
            ORDER BY {order_prefix} m.last_ts DESC
            LIMIT 1
        """, query_params).fetchone()

        if session:
            return session

        return conn.execute(f"""
            SELECT * FROM sessions s
            WHERE {where_sql}
            ORDER BY {order_prefix} s.started_at DESC
            LIMIT 1
        """, query_params).fetchone()

    def _get_session_columns(self, conn) -> List[str]:
        rows = conn.execute("PRAGMA table_info(sessions)").fetchall()
        columns = []
        for row in rows:
            if isinstance(row, sqlite3.Row):
                columns.append(row["name"])
            else:
                columns.append(row[1])
        return columns

    def _discover_agent_catalog(self, conn) -> dict:
        base_option = {
            "id": self.GLOBAL_AGENT_OPTION,
            "label": self.GLOBAL_AGENT_LABEL,
            "description": "使用全局最近 CLI 会话",
        }

        if not self.db_path.exists():
            return {
                "field": None,
                "mode": "global_cli_fallback",
                "reason": "database_missing",
                "supports_agent_selection": False,
                "options": [base_option],
            }

        if self._has_session_column(conn, "agent_id"):
            rows = conn.execute("""
                SELECT
                    s.agent_id AS value,
                    COUNT(*) AS session_count,
                    COALESCE(MAX(m.timestamp), MAX(s.started_at)) AS last_active
                FROM sessions s
                LEFT JOIN messages m ON m.session_id = s.id
                WHERE s.source = 'cli'
                  AND s.agent_id IS NOT NULL
                  AND TRIM(s.agent_id) != ''
                GROUP BY s.agent_id
                ORDER BY last_active DESC, s.agent_id ASC
            """).fetchall()

            options = [base_option]
            for row in rows:
                value = str(row["value"])
                label = value if len(value) <= 36 else value[:22] + "..." + value[-10:]
                options.append({
                    "id": value,
                    "label": label,
                    "description": f"sessions.agent_id = {value}",
                })

            return {
                "field": "agent_id",
                "mode": "field_available" if rows else "global_cli_fallback",
                "reason": "session_agent_id_available" if rows else "agent_id_column_empty",
                "supports_agent_selection": len(rows) > 0,
                "options": options,
            }

        return {
            "field": None,
            "mode": "global_cli_fallback",
            "reason": "agent_id_column_missing",
            "supports_agent_selection": False,
            "options": [base_option],
        }

    def _resolve_session_filter(self, conn) -> dict:
        catalog = self._discover_agent_catalog(conn)
        options = catalog["options"]
        option_map = {item["id"]: item for item in options}
        selected_agent = self.selected_agent or self.GLOBAL_AGENT_OPTION
        effective_selected = selected_agent if selected_agent in option_map else self.GLOBAL_AGENT_OPTION
        selected_option = option_map.get(effective_selected, options[0])

        if catalog["field"] == "agent_id" and effective_selected != self.GLOBAL_AGENT_OPTION:
            return {
                **catalog,
                "selected_agent": effective_selected,
                "selected_agent_label": selected_option["label"],
                "session_filter_field": "agent_id",
                "session_filter_value": effective_selected,
                "agent_filter_mode": "field_filter",
                "using_agent_id_filter": True,
                "fallback_to_legacy_null_agent": False,
            }

        mode = "global_cli_selected" if catalog["field"] else "global_cli_fallback"
        return {
            **catalog,
            "selected_agent": effective_selected,
            "selected_agent_label": selected_option["label"],
            "session_filter_field": "source",
            "session_filter_value": "cli",
            "agent_filter_mode": mode,
            "using_agent_id_filter": False,
            "fallback_to_legacy_null_agent": False,
        }

    def get_available_agents(self) -> Tuple[List[Dict], Dict]:
        if not self.db_path.exists():
            options = [{
                "id": self.GLOBAL_AGENT_OPTION,
                "label": self.GLOBAL_AGENT_LABEL,
                "description": "数据库不存在，使用全局最近 CLI 会话",
            }]
            return options, {
                "field": None,
                "mode": "global_cli_fallback",
                "reason": "database_missing",
                "supports_agent_selection": False,
                "selected_agent": self.GLOBAL_AGENT_OPTION,
                "selected_agent_label": self.GLOBAL_AGENT_LABEL,
                "session_filter_field": "source",
                "session_filter_value": "cli",
                "agent_filter_mode": "global_cli_fallback",
                "options": options,
            }

        conn = None
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            filter_info = self._resolve_session_filter(conn)
            return filter_info["options"], filter_info
        except Exception:
            options = [{
                "id": self.GLOBAL_AGENT_OPTION,
                "label": self.GLOBAL_AGENT_LABEL,
                "description": "读取 agent 列表失败，使用全局最近 CLI 会话",
            }]
            return options, {
                "field": None,
                "mode": "global_cli_fallback",
                "reason": "agent_catalog_error",
                "supports_agent_selection": False,
                "selected_agent": self.GLOBAL_AGENT_OPTION,
                "selected_agent_label": self.GLOBAL_AGENT_LABEL,
                "session_filter_field": "source",
                "session_filter_value": "cli",
                "agent_filter_mode": "global_cli_fallback",
                "options": options,
            }
        finally:
            if conn:
                conn.close()

    def _fetch_session_candidates(self, conn, filter_info: dict, limit: int = 12) -> List[Dict]:
        if filter_info.get("using_agent_id_filter") and self._has_session_column(conn, "agent_id"):
            where_sql = "s.source = 'cli' AND (s.agent_id = ? OR s.agent_id IS NULL)"
            params = [str(filter_info["session_filter_value"])]
        else:
            where_sql, params = self._build_session_query_filter(filter_info)

        rows = conn.execute(f"""
            SELECT
                s.*,
                COALESCE(MAX(m.timestamp), s.started_at) AS last_active,
                (
                    SELECT role
                    FROM messages m2
                    WHERE m2.session_id = s.id
                    ORDER BY m2.timestamp DESC
                    LIMIT 1
                ) AS last_role,
                (
                    SELECT content
                    FROM messages m3
                    WHERE m3.session_id = s.id
                    ORDER BY m3.timestamp DESC
                    LIMIT 1
                ) AS last_content,
                (
                    SELECT tool_name
                    FROM messages m4
                    WHERE m4.session_id = s.id
                    ORDER BY m4.timestamp DESC
                    LIMIT 1
                ) AS last_tool_name,
                (
                    SELECT tool_calls
                    FROM messages m5
                    WHERE m5.session_id = s.id
                    ORDER BY m5.timestamp DESC
                    LIMIT 1
                ) AS last_tool_calls,
                (
                    SELECT reasoning
                    FROM messages m6
                    WHERE m6.session_id = s.id
                    ORDER BY m6.timestamp DESC
                    LIMIT 1
                ) AS last_reasoning
            FROM sessions s
            LEFT JOIN messages m ON m.session_id = s.id
            WHERE {where_sql}
            GROUP BY s.id
            ORDER BY last_active DESC, s.started_at DESC
            LIMIT ?
        """, params + [limit]).fetchall()

        sessions: List[Dict] = []
        for row in rows:
            item = dict(row)
            last_message = self._enrich_message({
                "role": item.get("last_role"),
                "content": item.get("last_content"),
                "tool_name": item.get("last_tool_name"),
                "tool_calls": item.get("last_tool_calls"),
                "reasoning": item.get("last_reasoning"),
                "timestamp": item.get("last_active"),
            })
            item["last_activity"] = last_message.get("activity", "")
            item["session_label"] = self._format_session_label(item)
            sessions.append(item)
        return sessions

    def _format_clock_time(self, timestamp_value) -> str:
        parsed = self._parse_timestamp(timestamp_value)
        if not parsed:
            return "--:--"
        return parsed.strftime("%H:%M")

    def _format_session_label(self, session: Dict) -> str:
        sid = str(session.get("id", ""))
        short_id = sid[-8:] if len(sid) >= 8 else sid
        time_text = self._format_clock_time(session.get("last_active") or session.get("started_at"))
        title = (session.get("title") or "").strip()
        activity = (session.get("last_activity") or "").strip()
        if title:
            summary = title
        elif activity:
            summary = activity
        else:
            summary = "最近会话"
        summary = self._truncate_text(summary, 28)
        return f"{time_text} · {short_id} · {summary}"

    def get_available_sessions(self, limit: int = 12) -> Tuple[List[Dict], Dict]:
        auto_option = {
            "id": DEFAULT_SESSION_AUTO,
            "label": "自动（最新会话）",
            "mode": "auto",
            "description": "跟随当前 agent 最近活跃会话",
        }
        if not self.db_path.exists():
            return [auto_option], {
                "selected_session_id": DEFAULT_SESSION_AUTO,
                "session_mode": self.session_mode,
                "resolved_session_id": None,
                "session_fallback_reason": "database_missing",
            }

        conn = None
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            filter_info = self._resolve_session_filter(conn)
            sessions = self._fetch_session_candidates(conn, filter_info, limit=limit)
            live_sessions = self._list_live_cli_sessions(limit=limit)
            seen_ids = {session["id"] for session in sessions}
            for live in live_sessions:
                if live["id"] in seen_ids:
                    continue
                live["last_activity"] = self._build_activity_summary({
                    "role": live.get("last_role"),
                    "content": live.get("last_content"),
                    "tool_name": live.get("last_tool_name"),
                    "tool_calls": live.get("last_tool_calls"),
                    "reasoning": live.get("last_reasoning"),
                })
                live["session_label"] = self._format_session_label(live)
                sessions.append(live)
            sessions.sort(key=lambda item: item.get("last_active") or 0, reverse=True)
            options = [auto_option] + [
                {
                    "id": session["id"],
                    "label": session["session_label"],
                    "mode": "manual",
                    "description": session.get("last_activity", ""),
                    "title": session.get("title"),
                    "message_count": session.get("message_count"),
                    "selection_source": session.get("selection_source", "database"),
                }
                for session in sessions
            ]
            return options, {
                "selected_session_id": self.selected_session_id,
                "session_mode": self.session_mode,
                "resolved_session_id": sessions[0]["id"] if sessions else None,
                "session_fallback_reason": None,
            }
        except Exception:
            return [auto_option], {
                "selected_session_id": DEFAULT_SESSION_AUTO,
                "session_mode": DEFAULT_SESSION_MODE,
                "resolved_session_id": None,
                "session_fallback_reason": "session_catalog_error",
            }
        finally:
            if conn:
                conn.close()

    def _build_session_query_filter(self, filter_info: dict) -> Tuple[str, List[str]]:
        where_clauses = ["s.source = 'cli'"]
        params: List[str] = []

        filter_field = filter_info.get("session_filter_field")
        filter_value = filter_info.get("session_filter_value")
        if filter_field and filter_field not in ("source",) and filter_value not in (None, ""):
            if filter_field != "agent_id":
                raise ValueError(f"Unsupported session filter field: {filter_field}")
            where_clauses.append(f"s.{filter_field} = ?")
            params.append(str(filter_value))

        return " AND ".join(where_clauses), params

    def _resolve_active_session(self, conn, filter_info: Optional[dict] = None) -> Tuple[Optional[dict], dict]:
        filter_info = filter_info or self._resolve_session_filter(conn)
        sessions = self._fetch_session_candidates(conn, filter_info, limit=12)
        live_sessions = self._list_live_cli_sessions(limit=12)
        metadata = {
            **filter_info,
            "session_mode": self.session_mode,
            "selected_session_id": self.selected_session_id,
            "resolved_session_id": None,
            "session_fallback_reason": None,
            "candidate_session_ids": [item.get("id") for item in sessions[:5]],
            "candidate_live_session_ids": [item.get("id") for item in live_sessions[:5]],
        }

        chosen, metadata = self._prefer_live_session_candidate(sessions, live_sessions, metadata)
        if chosen is None:
            return None, metadata
        return chosen, metadata

    def _get_recent_cli_session(self, conn, filter_info: Optional[dict] = None) -> Tuple[Optional[sqlite3.Row], dict]:
        """返回当前 agent + session_mode 下的 active session"""
        filter_info = filter_info or self._resolve_session_filter(conn)
        session, metadata = self._resolve_active_session(conn, filter_info)
        return session, metadata

    def _check_database(self) -> Optional[Tuple[str, str, dict]]:
        """直接查询数据库获取最新状态 - 最精准"""
        if not self.db_path.exists():
            return None

        conn = None
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row

            filter_info = self._resolve_session_filter(conn)
            session, filter_info = self._get_recent_cli_session(conn, filter_info)
            if not session:
                metadata = {
                    "selected_agent": filter_info["selected_agent"],
                    "selected_agent_label": filter_info["selected_agent_label"],
                    "selected_session_id": filter_info.get("selected_session_id"),
                    "session_mode": filter_info.get("session_mode", DEFAULT_SESSION_MODE),
                    "resolved_session_id": filter_info.get("resolved_session_id"),
                    "session_filter_field": filter_info["session_filter_field"],
                    "session_filter_value": filter_info["session_filter_value"],
                    "agent_filter_mode": filter_info["agent_filter_mode"],
                    "agent_selection_supported": filter_info["supports_agent_selection"],
                    "using_agent_id_filter": filter_info.get("using_agent_id_filter", False),
                    "fallback_to_legacy_null_agent": filter_info.get("fallback_to_legacy_null_agent", False),
                    "session_fallback_reason": filter_info.get("session_fallback_reason"),
                    "status_reason": "no_session_for_selected_agent",
                    "message_count": 0,
                }
                return self.WAITING, "等待指令", metadata

            session_id = session['id']

            session_exists_in_db = isinstance(session, sqlite3.Row) or bool(session.get('selection_source') != 'live_session_json')
            history = self._fetch_recent_messages(conn, session_id, limit=10) if session_exists_in_db else []
            history, live_last_updated = self._load_live_session_messages(session_id, history)
            last_msg = history[-1] if history else None

            if history:
                self._emit_history_if_changed(history)

            session_dict = dict(session)
            total_tokens = (
                (session_dict.get('input_tokens') or 0)
                + (session_dict.get('output_tokens') or 0)
                + (session_dict.get('reasoning_tokens') or 0)
            )
            token_data_available = total_tokens > 0
            metadata = {
                'session_id': session_id,
                'message_count': session_dict.get('message_count', 0),
                'model': session_dict.get('model', 'unknown'),
                'input_tokens': session_dict.get('input_tokens', 0),
                'output_tokens': session_dict.get('output_tokens', 0),
                'reasoning_tokens': session_dict.get('reasoning_tokens', 0),
                'token_data_available': token_data_available,
                'selected_agent': filter_info['selected_agent'],
                'selected_agent_label': filter_info['selected_agent_label'],
                'selected_session_id': filter_info.get('selected_session_id'),
                'session_mode': filter_info.get('session_mode', DEFAULT_SESSION_MODE),
                'resolved_session_id': filter_info.get('resolved_session_id', session_id),
                'session_filter_field': filter_info['session_filter_field'],
                'session_filter_value': filter_info['session_filter_value'],
                'agent_filter_mode': filter_info['agent_filter_mode'],
                'agent_selection_supported': filter_info['supports_agent_selection'],
                'available_agent_field': filter_info.get('field'),
                'using_agent_id_filter': filter_info.get('using_agent_id_filter', False),
                'fallback_to_legacy_null_agent': filter_info.get('fallback_to_legacy_null_agent', False),
                'session_fallback_reason': filter_info.get('session_fallback_reason'),
                'recent_activity': [msg.get('activity') for msg in history[-6:] if msg.get('activity')],
                'recent_files': [item for msg in history[-6:] for item in msg.get('attachments', [])][:4],
                'live_session_last_updated': live_last_updated,
                'status_reason': 'no_messages',
                'last_message_age': None,
                'last_message_role': None,
                'last_message_timestamp': None,
            }

            metadata.update({
                'session_selection_reason': filter_info.get('session_selection_reason'),
                'session_json_exists': filter_info.get('session_json_exists'),
                'session_exists_in_db': filter_info.get('session_exists_in_db'),
                'candidate_session_ids': filter_info.get('candidate_session_ids', []),
                'candidate_live_session_ids': filter_info.get('candidate_live_session_ids', []),
                'db_latest_session_id': filter_info.get('db_latest_session_id'),
                'db_latest_last_active': filter_info.get('db_latest_last_active'),
            })

            assistant_messages = sum(1 for msg in history if msg.get('role') == 'assistant')
            self.performance.update({
                "api_calls": assistant_messages,
                "total_tokens": total_tokens,
                "input_tokens": session_dict.get('input_tokens', 0) or 0,
                "output_tokens": session_dict.get('output_tokens', 0) or 0,
                "reasoning_tokens": session_dict.get('reasoning_tokens', 0) or 0,
                "message_count": session_dict.get('message_count', 0) or 0,
                "token_data_available": token_data_available,
            })

            if not last_msg:
                metadata['status_reason'] = 'session_has_no_messages'
                return self.WAITING, "等待输入", metadata

            role = last_msg.get('role', '')
            content = self._extract_content_text(last_msg.get('raw_content', last_msg.get('content')), '处理中...')
            tool_name = last_msg.get('tool_name')
            tool_calls = last_msg.get('tool_calls')
            last_timestamp = last_msg.get('timestamp')
            last_age = self._message_age_seconds(last_timestamp)

            metadata.update({
                'last_message_age': round(last_age, 1) if last_age is not None else None,
                'last_message_role': role,
                'last_message_timestamp': last_timestamp,
            })

            if metadata.get("cron_overdue"):
                metadata['health_level'] = 'red'
            elif metadata.get("cron_last_status") in {'error', 'failed'}:
                metadata['health_level'] = 'red'
            elif self._healthy_recent_cron_success(metadata):
                metadata['health_level'] = 'green'
            else:
                metadata['health_level'] = 'yellow'

            detail = content[:100] + "..." if len(content) > 100 else content
            if not detail or detail == 'None':
                detail = "等待指令"

            if last_age is not None and last_age > 300:
                metadata['status_reason'] = 'message_stale_over_300s'
                if role == 'assistant':
                    return self.WAITING, detail, metadata
                return self.IDLE, "空闲中", metadata

            if role == 'user':
                if last_age is None or last_age <= 60:
                    metadata['status_reason'] = 'recent_user_message_within_60s'
                    top_detail = self._top_detail_from_activity(last_msg, self.THINKING) or "思考中..."
                    return self.THINKING, top_detail, metadata
                metadata['status_reason'] = 'user_message_not_recent'
                return self.WAITING, detail, metadata

            if role == 'assistant':
                if tool_calls:
                    try:
                        calls = json.loads(tool_calls) if isinstance(tool_calls, str) else tool_calls
                    except (json.JSONDecodeError, TypeError):
                        calls = tool_calls

                    if isinstance(calls, list) and len(calls) > 0:
                        if last_age is None or last_age <= 90:
                            metadata['status_reason'] = 'recent_assistant_tool_calls_within_90s'
                            top_detail = self._top_detail_from_activity(last_msg, self.WORKING) or detail or "最近有新动作"
                            return self.WORKING, top_detail, metadata
                        metadata['status_reason'] = 'assistant_tool_calls_stale'
                        return self.WAITING, detail, metadata

                metadata['status_reason'] = 'assistant_text_reply_waiting'
                top_detail = self._top_detail_from_activity(last_msg, self.WAITING) or detail
                return self.WAITING, top_detail, metadata

            if role == 'tool':
                if last_age is None or last_age <= 60:
                    metadata['status_reason'] = 'recent_tool_message_within_60s'
                    top_detail = self._top_detail_from_activity(last_msg, self.WORKING) or detail or "最近有新动作"
                    return self.WORKING, top_detail, metadata
                metadata['status_reason'] = 'tool_message_not_recent'
                top_detail = self._top_detail_from_activity(last_msg, self.WAITING) or detail
                return self.WAITING, top_detail, metadata

            metadata['status_reason'] = 'fallback_waiting'
            return self.WAITING, detail, metadata

        except Exception as e:
            print(f"数据库查询错误: {e}")
            return None
        finally:
            if conn:
                conn.close()

    def get_recent_history(self, count: int = 5) -> List[Dict]:
        """获取最近的消息历史 - 跟随当前选中的 agent"""
        if not self.db_path.exists():
            return []

        conn = None
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row

            filter_info = self._resolve_session_filter(conn)
            session, session_meta = self._get_recent_cli_session(conn, filter_info)
            if not session:
                return []

            history = self._fetch_recent_messages(conn, session['id'], limit=max(count, 10)) if session_meta.get('session_exists_in_db', True) else []
            history, _ = self._load_live_session_messages(session['id'], history)
            return history[-count:]
        except Exception:
            return []
        finally:
            if conn:
                conn.close()


# ============================================================
# macOS 通知
# ============================================================
def send_macos_notification(title: str, message: str, sound: bool = True):
    if objc is None:
        return
    
    try:
        notification = NSUserNotification.alloc().init()
        notification.setTitle_(title)
        notification.setInformativeText_(message)
        
        if sound:
            notification.setSoundName_("default")
        
        center = NSUserNotificationCenter.defaultUserNotificationCenter()
        center.deliverNotification_(notification)
    except Exception as e:
        print(f"通知发送失败: {e}")


def play_sound(sound_name: str = "Glass"):
    if not SOUND_AVAILABLE:
        return
    
    try:
        sound = NSSound.soundNamed_(sound_name)
        if sound:
            sound.play()
    except Exception:
        pass


class HermesSendWorker(QThread):
    completed = pyqtSignal(bool, str, str)

    def __init__(self, message: str, agent_id: str = "", session_id: str = "", parent=None):
        super().__init__(parent)
        self.message = message
        self.agent_id = agent_id or ""
        self.session_id = session_id or ""

    def run(self):
        env = os.environ.copy()
        if self.agent_id and self.agent_id != DEFAULT_AGENT_SELECTION:
            env["HERMES_AGENT_ID"] = self.agent_id
        else:
            env.pop("HERMES_AGENT_ID", None)

        cmd = ["hermes", "chat", "-q", self.message, "-Q"]
        if self.session_id:
            cmd.extend(["--resume", self.session_id])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=180,
                env=env,
            )
            success = result.returncode == 0
            self.completed.emit(success, (result.stdout or "").strip(), (result.stderr or "").strip())
        except Exception as e:
            self.completed.emit(False, "", str(e))


# ============================================================
# 状态指示点
# ============================================================
class StatusDot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.dot_color = QColor("#8E8E93")
        self.setFixedSize(12, 12)
        self._pulse_anim = None
        self._pulse_value = 1.0

    def set_color(self, color: str):
        self.dot_color = QColor(color)
        self.update()

    def set_pulsing(self, pulsing: bool):
        if pulsing and self._pulse_anim is None:
            self._pulse_anim = QPropertyAnimation(self, b"pulse_value")
            self._pulse_anim.setDuration(1000)
            self._pulse_anim.setStartValue(1.0)
            self._pulse_anim.setEndValue(0.4)
            self._pulse_anim.setLoopCount(-1)
            self._pulse_anim.setEasingCurve(QEasingCurve.InOutSine)
            self._pulse_anim.start()
        elif not pulsing and self._pulse_anim:
            self._pulse_anim.stop()
            self._pulse_anim = None
            self._pulse_value = 1.0
            self.update()

    def get_pulse_value(self):
        return self._pulse_value

    def set_pulse_value(self, value):
        self._pulse_value = value
        self.update()

    pulse_value = pyqtProperty(float, get_pulse_value, set_pulse_value)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        color = QColor(self.dot_color)
        color.setAlphaF(self._pulse_value)
        
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(self.rect())


# ============================================================
# 聊天输入框 - 修复字体颜色
# ============================================================
class ChatInput(QFrame):
    message_sent = pyqtSignal(str)
    
    def __init__(self, parent=None, theme_config: ThemeConfig = None):
        super().__init__(parent)
        self.theme_config = theme_config or THEMES[Theme.DARK]
        self.setObjectName("chatInput")
        self.setup_ui()
    
    def setup_ui(self):
        self.setFixedHeight(74)
        
        self.apply_theme()
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)
        
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("输入消息...")
        self.apply_input_style()
        self.input_field.returnPressed.connect(self.send_message)
        top_row.addWidget(self.input_field, 1)
        
        self.send_btn = QPushButton("发送")
        self.send_btn.setFixedSize(56, 32)
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.apply_button_style()
        self.send_btn.clicked.connect(self.send_message)
        top_row.addWidget(self.send_btn)
        layout.addLayout(top_row)

        self.status_label = QLabel("就绪")
        self.status_label.setObjectName("chatStatusLabel")
        self.status_label.setWordWrap(False)
        self.status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(self.status_label)

    def apply_button_style(self):
        self.send_btn.setStyleSheet(f"""
            QPushButton {{
                background: {self.theme_config.accent_color};
                border: none;
                border-radius: 14px;
                color: white;
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
            QPushButton:pressed {{
                opacity: 0.7;
            }}
        """)
    
    def apply_theme(self):
        self.setStyleSheet(f"""
            QFrame#chatInput {{
                background: {self.theme_config.input_bg};
                border: 1px solid {self.theme_config.border_color};
                border-radius: 20px;
            }}
            QLabel#chatStatusLabel {{
                color: {self.theme_config.text_secondary};
                font-size: 11px;
                padding-left: 4px;
            }}
        """)
    
    def apply_input_style(self):
        self.input_field.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(255, 255, 255, 15);
                border: 1px solid {self.theme_config.border_color};
                border-radius: 14px;
                padding: 6px 14px;
                color: {self.theme_config.input_text};
                font-size: 13px;
            }}
            QLineEdit:focus {{
                background: rgba(255, 255, 255, 20);
                border-color: {self.theme_config.accent_color};
            }}
        """)
    
    def update_theme(self, theme_config: ThemeConfig):
        self.theme_config = theme_config
        self.apply_theme()
        self.apply_input_style()
        self.apply_button_style()

    def set_status_text(self, text: str, error: bool = False):
        color = "#FF453A" if error else self.theme_config.text_secondary
        self.status_label.setStyleSheet(f"color: {color}; font-size: 11px; padding-left: 4px;")
        self.status_label.setText(text)

    def set_busy(self, busy: bool):
        self.send_btn.setEnabled(not busy)
        self.input_field.setEnabled(not busy)
    
    def send_message(self):
        text = self.input_field.text().strip()
        if text:
            self.message_sent.emit(text)
            self.input_field.clear()
    
    def focus_input(self):
        self.input_field.setFocus()
        self.input_field.selectAll()


# ============================================================
# 历史消息面板 - 修复字体颜色
# ============================================================
class HistoryPanel(QFrame):
    message_clicked = pyqtSignal(str)
    
    def __init__(self, parent=None, theme_config: ThemeConfig = None):
        super().__init__(parent)
        self.theme_config = theme_config or THEMES[Theme.DARK]
        self.setObjectName("historyPanel")
        self.last_messages: List[Dict] = []
        self.setup_ui()
    
    def setup_ui(self):
        self.setMinimumHeight(180)
        self.apply_theme()
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        self.title_label = QLabel("最近消息")
        self.title_label.setObjectName("titleLabel")
        self.title_label.setStyleSheet(f"""
            QLabel#titleLabel {{
                color: {self.theme_config.text_secondary};
                font-size: 12px;
                font-weight: 500;
                background: transparent;
            }}
        """)
        layout.addWidget(self.title_label)
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("background: transparent;")
        layout.addWidget(self.scroll, 1)

        self.messages_container = QWidget()
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.setContentsMargins(0, 0, 0, 0)
        self.messages_layout.setSpacing(6)
        self.messages_layout.addStretch()
        self.scroll.setWidget(self.messages_container)
    
    def apply_theme(self):
        self.setStyleSheet(f"""
            QFrame#historyPanel {{
                background: rgba(25, 25, 30, 240);
                border: 1px solid {self.theme_config.border_color};
                border-radius: 16px;
            }}
        """)
        if hasattr(self, "title_label"):
            self.title_label.setStyleSheet(f"""
                QLabel#titleLabel {{
                    color: {self.theme_config.text_secondary};
                    font-size: 12px;
                    font-weight: 500;
                    background: transparent;
                }}
            """)

    def update_theme(self, theme_config: ThemeConfig):
        self.theme_config = theme_config
        self.apply_theme()
        self.update_history(self.last_messages)
    
    def update_history(self, messages: List[Dict]):
        self.last_messages = [dict(msg) if not isinstance(msg, dict) else msg.copy() for msg in messages]
        while self.messages_layout.count():
            item = self.messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        for msg in self.last_messages:
            # 确保 msg 是字典类型（可能传入的是 sqlite3.Row）
            if not isinstance(msg, dict):
                msg = dict(msg)
            
            role = msg.get("role", "")
            content = msg.get("content", "")
            
            if isinstance(content, str) and content.startswith('['):
                try:
                    content = json.loads(content)
                except:
                    pass
            
            if isinstance(content, list):
                text_parts = [item.get("text", "") for item in content if item.get("type") == "text"]
                content = " ".join(text_parts) if text_parts else "[多模态内容]"
            
            if not content or content == 'None':
                continue
            
            display_text = content[:60] + "..." if len(content) > 60 else content
            
            label = QLabel()
            label.setWordWrap(True)
            label.setCursor(Qt.PointingHandCursor)
            
            if role == "user":
                label.setText(f"你: {display_text}")
                label.setStyleSheet(f"""
                    QLabel {{
                        color: {self.theme_config.accent_color};
                        font-size: 11px;
                        background: transparent;
                        padding: 4px;
                    }}
                    QLabel:hover {{
                        background: rgba(48, 209, 88, 30);
                        border-radius: 6px;
                    }}
                """)
            elif role == "assistant":
                label.setText(f"Hermes: {display_text}")
                label.setStyleSheet(f"""
                    QLabel {{
                        color: {self.theme_config.text_color};
                        font-size: 11px;
                        background: transparent;
                        padding: 4px;
                    }}
                    QLabel:hover {{
                        background: rgba(255, 255, 255, 20);
                        border-radius: 6px;
                    }}
                """)
            elif role == "tool":
                activity = msg.get("activity") or content[:60] or "最近活动"
                label.setText(activity)
                label.setStyleSheet(f"""
                    QLabel {{
                        color: {self.theme_config.text_secondary};
                        font-size: 11px;
                        background: transparent;
                        padding: 4px;
                    }}
                    QLabel:hover {{
                        background: rgba(255, 255, 255, 20);
                        border-radius: 6px;
                    }}
                """)
            else:
                continue
            
            label.mousePressEvent = lambda e, c=content: self.message_clicked.emit(c)
            
            self.messages_layout.addWidget(label)
        self.messages_layout.addStretch()


class ActivityPanel(QFrame):
    def __init__(self, parent=None, theme_config: ThemeConfig = None):
        super().__init__(parent)
        self.theme_config = theme_config or THEMES[Theme.DARK]
        self.setObjectName("activityPanel")
        self.events: List[Dict] = []
        self.setup_ui()

    def setup_ui(self):
        self.setMinimumHeight(210)
        self.apply_theme()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.title_label = QLabel("最近动作")
        self.title_label.setStyleSheet(f"""
            QLabel {{
                color: {self.theme_config.text_secondary};
                font-size: 12px;
                font-weight: 500;
                background: transparent;
            }}
        """)
        layout.addWidget(self.title_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("background: transparent;")
        layout.addWidget(self.scroll, 1)

        self.events_container = QWidget()
        self.events_layout = QVBoxLayout(self.events_container)
        self.events_layout.setContentsMargins(0, 0, 0, 0)
        self.events_layout.setSpacing(8)
        self.events_layout.addStretch()
        self.scroll.setWidget(self.events_container)

    def apply_theme(self):
        self.setStyleSheet(f"""
            QFrame#activityPanel {{
                background: rgba(25, 25, 30, 240);
                border: 1px solid {self.theme_config.border_color};
                border-radius: 16px;
            }}
        """)
        if hasattr(self, "title_label"):
            self.title_label.setStyleSheet(f"""
                QLabel {{
                    color: {self.theme_config.text_secondary};
                    font-size: 12px;
                    font-weight: 500;
                    background: transparent;
                }}
            """)

    def update_theme(self, theme_config: ThemeConfig):
        self.theme_config = theme_config
        self.apply_theme()
        self.update_events(self.events)

    def update_events(self, messages: List[Dict]):
        self.events = [dict(msg) if not isinstance(msg, dict) else msg.copy() for msg in messages]
        while self.events_layout.count():
            item = self.events_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for msg in self.events[-8:]:
            role = msg.get("role", "")
            activity = msg.get("activity") or msg.get("content") or "最近活动"
            attachments = msg.get("attachments") or []
            timestamp = msg.get("timestamp")

            if role == "tool":
                activity_text = (activity or "").strip()
                if activity_text.startswith("📚"):
                    tag = "Skill"
                elif activity_text.startswith("📋"):
                    tag = "Plan"
                elif activity_text.startswith("📖"):
                    tag = "Read"
                elif activity_text.startswith("🔎"):
                    tag = "Grep"
                elif activity_text.startswith("🔍"):
                    tag = "Search"
                elif activity_text.startswith("🧩"):
                    tag = "Delegate"
                elif activity_text.startswith("🧠"):
                    tag = "Memory"
                elif activity_text.startswith(("🖱", "⌨️", "↕️", "🧪", "👁", "🖼", "↩️", "🌐", "📸")):
                    tag = "Browser"
                else:
                    tag = "工具"
                color = self.theme_config.accent_color
            elif role == "assistant":
                color = self.theme_config.text_color
                tag = "Hermes"
            elif role == "user":
                color = self.theme_config.accent_color
                tag = "你"
            else:
                color = self.theme_config.text_secondary
                tag = role or "事件"

            card = QFrame()
            card.setStyleSheet(f"""
                QFrame {{
                    background: rgba(255, 255, 255, 12);
                    border-radius: 10px;
                }}
            """)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(10, 8, 10, 8)
            card_layout.setSpacing(4)

            header = QLabel(tag)
            header.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 600; background: transparent;")
            card_layout.addWidget(header)

            body = QLabel(activity)
            body.setWordWrap(True)
            body.setStyleSheet(f"color: {self.theme_config.text_color}; font-size: 12px; background: transparent;")
            card_layout.addWidget(body)

            if attachments:
                names = ", ".join(Path(item).name or item for item in attachments[:2])
                attach = QLabel(f"附件: {names}")
                attach.setWordWrap(True)
                attach.setStyleSheet(f"color: {self.theme_config.text_secondary}; font-size: 11px; background: transparent;")
                card_layout.addWidget(attach)

            if timestamp is not None:
                age = self._format_age(timestamp)
                meta = QLabel(age)
                meta.setStyleSheet(f"color: {self.theme_config.text_secondary}; font-size: 10px; background: transparent;")
                card_layout.addWidget(meta)

            self.events_layout.addWidget(card)

        self.events_layout.addStretch()

    def _format_age(self, timestamp_value) -> str:
        if not isinstance(timestamp_value, (int, float)):
            return ""
        age = max(0, int(time.time() - float(timestamp_value)))
        if age < 60:
            return f"{age}s 前"
        if age < 3600:
            return f"{age // 60}m 前"
        return f"{age // 3600}h 前"


# ============================================================
# 性能仪表板 - 修复字体颜色
# ============================================================
class PerformancePanel(QFrame):
    def __init__(self, parent=None, theme_config: ThemeConfig = None):
        super().__init__(parent)
        self.theme_config = theme_config or THEMES[Theme.DARK]
        self.setObjectName("performancePanel")
        self.last_stats: Dict = {}
        self.setup_ui()
    
    def setup_ui(self):
        self.setFixedHeight(136)
        self.apply_theme()
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)
        
        self.title_label = QLabel("📊 性能统计")
        self.title_label.setStyleSheet(f"""
            QLabel {{
                color: {self.theme_config.text_secondary};
                font-size: 12px;
                font-weight: 500;
                background: transparent;
            }}
        """)
        layout.addWidget(self.title_label)
        
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(16)
        
        self.api_calls_label = self.create_stat_label("API 调用", "0")
        stats_layout.addWidget(self.api_calls_label)
        
        self.response_time_label = self.create_stat_label("Tokens", "-")
        stats_layout.addWidget(self.response_time_label)
        
        self.tokens_label = self.create_stat_label("消息数", "-")
        stats_layout.addWidget(self.tokens_label)
        
        layout.addLayout(stats_layout)
        self.hint_label = QLabel("暂无有效 token 数据")
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet(f"""
            QLabel {{
                color: {self.theme_config.text_secondary};
                font-size: 11px;
                background: transparent;
            }}
        """)
        self.hint_label.hide()
        layout.addWidget(self.hint_label)
        layout.addStretch()
    
    def apply_theme(self):
        self.setStyleSheet(f"""
            QFrame#performancePanel {{
                background: rgba(25, 25, 30, 240);
                border: 1px solid {self.theme_config.border_color};
                border-radius: 16px;
            }}
        """)
        if hasattr(self, "title_label"):
            self.title_label.setStyleSheet(f"""
                QLabel {{
                    color: {self.theme_config.text_secondary};
                    font-size: 12px;
                    font-weight: 500;
                    background: transparent;
                }}
            """)

    def update_theme(self, theme_config: ThemeConfig):
        self.theme_config = theme_config
        self.apply_theme()
        for label in self.findChildren(QLabel, "value"):
            label.setStyleSheet(f"""
                QLabel {{
                    color: {self.theme_config.accent_color};
                    font-size: 18px;
                    font-weight: 600;
                    background: transparent;
                }}
            """)
        for label in self.findChildren(QLabel, "name"):
            label.setStyleSheet(f"""
                QLabel {{
                    color: {self.theme_config.text_secondary};
                    font-size: 10px;
                    background: transparent;
                }}
            """)
        self.hint_label.setStyleSheet(f"""
            QLabel {{
                color: {self.theme_config.text_secondary};
                font-size: 11px;
                background: transparent;
            }}
        """)
        self.update_stats(self.last_stats or {})
    
    def create_stat_label(self, name: str, value: str) -> QWidget:
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        
        value_label = QLabel(value)
        value_label.setObjectName("value")
        value_label.setStyleSheet(f"""
            QLabel {{
                color: {self.theme_config.accent_color};
                font-size: 18px;
                font-weight: 600;
                background: transparent;
            }}
        """)
        layout.addWidget(value_label)
        
        name_label = QLabel(name)
        name_label.setObjectName("name")
        name_label.setStyleSheet(f"""
            QLabel {{
                color: {self.theme_config.text_secondary};
                font-size: 10px;
                background: transparent;
            }}
        """)
        layout.addWidget(name_label)
        
        return container
    
    def update_stats(self, stats: Dict):
        self.last_stats = stats.copy()
        api_calls = stats.get("api_calls", 0)
        tokens = stats.get("total_tokens", 0)
        message_count = stats.get("message_count", 0)
        token_data_available = stats.get("token_data_available", False)
        input_tokens = stats.get("input_tokens", 0)
        output_tokens = stats.get("output_tokens", 0)
        reasoning_tokens = stats.get("reasoning_tokens", 0)
        
        api_label = self.api_calls_label.findChild(QLabel, "value")
        if api_label:
            api_label.setText(str(api_calls))
        
        tokens_label = self.response_time_label.findChild(QLabel, "value")
        if tokens_label:
            if token_data_available and tokens > 0:
                tokens_label.setText(f"{tokens/1000:.1f}K" if tokens >= 1000 else str(tokens))
            else:
                tokens_label.setText("-")
        
        msg_label = self.tokens_label.findChild(QLabel, "value")
        if msg_label:
            msg_label.setText(str(message_count) if message_count > 0 else "-")

        if token_data_available and tokens > 0:
            self.hint_label.setText(
                f"输入 {input_tokens} · 输出 {output_tokens} · 推理 {reasoning_tokens}"
            )
            self.hint_label.show()
        else:
            self.hint_label.setText("暂无有效 token 数据")
            self.hint_label.show()


# ============================================================
# 主题设置对话框 - 修复字体颜色
# ============================================================
class ThemeDialog(QDialog):
    theme_changed = pyqtSignal(str, dict, int)
    agent_changed = pyqtSignal(str)
    session_changed = pyqtSignal(str, str)
    
    def __init__(
        self,
        current_theme: str,
        status_colors: Dict,
        current_opacity: int,
        agent_options: List[Dict],
        selected_agent: str,
        agent_info: Dict,
        session_options: List[Dict],
        session_mode: str,
        selected_session_id: str,
        parent=None,
    ):
        super().__init__(parent)
        self.current_theme = current_theme
        self.status_colors = status_colors.copy()
        self.current_opacity = current_opacity
        self.agent_options = agent_options
        self.selected_agent = selected_agent
        self.agent_info = agent_info or {}
        self.session_options = session_options
        self.session_mode = session_mode or DEFAULT_SESSION_MODE
        self.selected_session_id = selected_session_id or DEFAULT_SESSION_AUTO
        self.setup_ui()
    
    def setup_ui(self):
        self.setWindowTitle("主题与 Agent 设置")
        self.resize(380, 560)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("""
            QDialog {
                background: rgba(30, 30, 35, 250);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 12px;
            }
            QLabel {
                color: rgba(255, 255, 255, 238);
            }
            QGroupBox {
                color: rgba(255, 255, 255, 200);
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 16px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
            }
            QComboBox {
                background: rgba(255, 255, 255, 15);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 6px;
                padding: 6px 12px;
                color: rgba(255, 255, 255, 238);
                selection-background-color: rgba(48, 209, 88, 90);
                selection-color: rgba(255, 255, 255, 238);
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid rgba(255, 255, 255, 150);
                margin-right: 8px;
            }
            QComboBox QAbstractItemView {
                background: rgb(18, 18, 22);
                color: rgba(255, 255, 255, 238);
                border: 1px solid rgba(255, 255, 255, 30);
                selection-background-color: rgba(48, 209, 88, 110);
                selection-color: rgba(255, 255, 255, 255);
                outline: 0;
                padding: 4px;
            }
            QComboBox QAbstractItemView::item {
                min-height: 26px;
                padding: 4px 8px;
                background: rgb(18, 18, 22);
                color: rgba(255, 255, 255, 238);
            }
            QComboBox QAbstractItemView::item:selected {
                background: rgba(48, 209, 88, 110);
                color: rgba(255, 255, 255, 255);
            }
            QAbstractScrollArea {
                background: rgb(18, 18, 22);
                color: rgba(255, 255, 255, 238);
            }
            QSlider::groove:horizontal {
                background: rgba(255, 255, 255, 30);
                height: 6px;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: rgba(48, 209, 88, 240);
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }
            QPushButton {
                background: rgba(48, 209, 88, 200);
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
                color: white;
                font-weight: 500;
            }
            QPushButton:hover {
                background: rgba(48, 209, 88, 240);
            }
            QScrollArea#settingsScroll {
                background: rgba(30, 30, 35, 220);
                border: none;
            }
            QWidget#settingsContent {
                background: rgba(30, 30, 35, 220);
            }
            QWidget#settingsViewport {
                background: rgba(30, 30, 35, 220);
            }
        """)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(12, 12, 12, 12)
        outer_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setObjectName("settingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.viewport().setObjectName("settingsViewport")
        outer_layout.addWidget(scroll)

        content = QWidget()
        content.setObjectName("settingsContent")
        scroll.setWidget(content)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(16)
        
        theme_group = QGroupBox("主题模式")
        theme_layout = QVBoxLayout(theme_group)
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["深色", "浅色"])
        self.theme_combo.setCurrentIndex(0 if self.current_theme == "dark" else 1)
        theme_layout.addWidget(self.theme_combo)
        
        layout.addWidget(theme_group)

        agent_group = QGroupBox("Agent 选择")
        agent_layout = QVBoxLayout(agent_group)
        agent_layout.setSpacing(10)

        agent_row = QHBoxLayout()
        agent_row.setContentsMargins(0, 0, 0, 0)
        agent_row.setSpacing(8)

        self.agent_combo = QComboBox()
        self.agent_combo.currentIndexChanged.connect(self.on_agent_changed)
        agent_row.addWidget(self.agent_combo, 1)

        self.refresh_agent_btn = QPushButton("刷新")
        self.refresh_agent_btn.setFixedWidth(72)
        self.refresh_agent_btn.clicked.connect(self.refresh_agents)
        agent_row.addWidget(self.refresh_agent_btn)

        agent_layout.addLayout(agent_row)

        self.agent_hint_label = QLabel()
        self.agent_hint_label.setWordWrap(True)
        self.agent_hint_label.setStyleSheet("""
            QLabel {
                color: rgba(255, 255, 255, 150);
                font-size: 11px;
            }
        """)
        agent_layout.addWidget(self.agent_hint_label)

        self.update_agent_options(self.agent_options, self.agent_info, self.selected_agent)
        layout.addWidget(agent_group)

        session_group = QGroupBox("会话选择")
        session_layout = QVBoxLayout(session_group)
        session_layout.setSpacing(10)

        self.session_combo = QComboBox()
        self.session_combo.currentIndexChanged.connect(self.on_session_changed)
        session_layout.addWidget(self.session_combo)

        self.session_hint_label = QLabel()
        self.session_hint_label.setWordWrap(True)
        self.session_hint_label.setStyleSheet("""
            QLabel {
                color: rgba(255, 255, 255, 150);
                font-size: 11px;
            }
        """)
        session_layout.addWidget(self.session_hint_label)

        self.update_session_options(self.session_options, self.session_mode, self.selected_session_id)
        layout.addWidget(session_group)
        
        opacity_group = QGroupBox("透明度")
        opacity_layout = QVBoxLayout(opacity_group)
        
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(50, 100)
        self.opacity_slider.setValue(self.current_opacity)
        opacity_layout.addWidget(self.opacity_slider)
        
        self.opacity_label = QLabel(f"{self.current_opacity}%")
        self.opacity_label.setAlignment(Qt.AlignCenter)
        opacity_layout.addWidget(self.opacity_label)
        
        self.opacity_slider.valueChanged.connect(lambda v: self.opacity_label.setText(f"{v}%"))
        
        layout.addWidget(opacity_group)
        
        colors_group = QGroupBox("状态颜色")
        colors_layout = QFormLayout(colors_group)
        
        self.color_buttons = {}
        status_names = {
            "idle": "空闲",
            "thinking": "思考中",
            "working": "工作中",
            "waiting": "等待中",
            "error": "错误"
        }
        
        for status, name in status_names.items():
            btn = QPushButton()
            btn.setFixedSize(60, 28)
            color = self.status_colors.get(status, "#8E8E93")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {color};
                    border: 1px solid rgba(255, 255, 255, 30);
                    border-radius: 6px;
                }}
            """)
            btn.clicked.connect(lambda checked, s=status: self.pick_color(s))
            self.color_buttons[status] = btn
            colors_layout.addRow(name, btn)
        
        layout.addWidget(colors_group)
        
        apply_btn = QPushButton("应用")
        apply_btn.clicked.connect(self.apply_theme)
        layout.addWidget(apply_btn)
        self._apply_combo_popup_theme()

    def _apply_combo_popup_theme(self):
        popup_style = """
            QListView {
                background: rgb(18, 18, 22);
                color: rgba(255, 255, 255, 238);
                border: 1px solid rgba(255, 255, 255, 30);
                outline: 0;
            }
            QListView::item {
                min-height: 26px;
                padding: 4px 8px;
                background: rgb(18, 18, 22);
                color: rgba(255, 255, 255, 238);
            }
            QListView::item:selected {
                background: rgba(48, 209, 88, 110);
                color: rgba(255, 255, 255, 255);
            }
        """
        for combo in (self.theme_combo, self.agent_combo, self.session_combo):
            view = combo.view()
            if view:
                view.setStyleSheet(popup_style)

    def _build_agent_hint(self) -> str:
        field = self.agent_info.get("field")
        if field:
            return f"当前按 sessions.{field} 区分 agent，切换后会立即更新状态检测和历史记录。"
        return "当前数据库无法可靠区分 agent，已降级为使用全局最近 CLI 会话。"

    def update_agent_options(self, agent_options: List[Dict], agent_info: Dict, selected_agent: str = None):
        self.agent_options = agent_options or [{
            "id": DEFAULT_AGENT_SELECTION,
            "label": DEFAULT_AGENT_LABEL,
            "description": "使用全局最近 CLI 会话",
        }]
        self.agent_info = agent_info or {}
        self.selected_agent = selected_agent or self.agent_info.get("selected_agent") or self.selected_agent

        self.agent_combo.blockSignals(True)
        self.agent_combo.clear()
        current_index = 0
        for index, item in enumerate(self.agent_options):
            self.agent_combo.addItem(item["label"], item["id"])
            if item["id"] == self.selected_agent:
                current_index = index
        self.agent_combo.setCurrentIndex(current_index)
        self.agent_combo.blockSignals(False)
        self.agent_hint_label.setText(self._build_agent_hint())

    def update_session_options(self, session_options: List[Dict], session_mode: str, selected_session_id: str):
        self.session_options = session_options or [{
            "id": DEFAULT_SESSION_AUTO,
            "label": "自动（最新会话）",
            "mode": "auto",
        }]
        self.session_mode = session_mode or DEFAULT_SESSION_MODE
        self.selected_session_id = selected_session_id or DEFAULT_SESSION_AUTO

        self.session_combo.blockSignals(True)
        self.session_combo.clear()
        current_index = 0
        for index, item in enumerate(self.session_options):
            self.session_combo.addItem(item["label"], (item.get("mode", "manual"), item["id"]))
            if item.get("mode", "manual") == self.session_mode and item["id"] == self.selected_session_id:
                current_index = index
            elif self.session_mode == "auto" and item["id"] == DEFAULT_SESSION_AUTO:
                current_index = index
        self.session_combo.setCurrentIndex(current_index)
        self.session_combo.blockSignals(False)
        self.session_hint_label.setText(
            "自动模式会跟随当前 agent 最新会话；选中具体会话后将锁定到该 session。"
        )

    def refresh_agents(self):
        parent = self.parent()
        if parent and hasattr(parent, "refresh_agent_options"):
            agent_options, agent_info = parent.refresh_agent_options(notify=False)
            self.update_agent_options(agent_options, agent_info, parent.current_instance)
        if parent and hasattr(parent, "refresh_session_options"):
            session_options, session_info = parent.refresh_session_options(notify=False)
            self.update_session_options(
                session_options,
                session_info.get("session_mode", DEFAULT_SESSION_MODE),
                session_info.get("selected_session_id", DEFAULT_SESSION_AUTO),
            )

    def on_agent_changed(self, index: int):
        agent_id = self.agent_combo.itemData(index)
        if not agent_id:
            return
        self.selected_agent = agent_id
        self.agent_changed.emit(agent_id)
        self.agent_hint_label.setText(self._build_agent_hint())
        parent = self.parent()
        if parent and hasattr(parent, "refresh_session_options"):
            session_options, session_info = parent.refresh_session_options(notify=False)
            self.update_session_options(
                session_options,
                session_info.get("session_mode", DEFAULT_SESSION_MODE),
                session_info.get("selected_session_id", DEFAULT_SESSION_AUTO),
            )

    def on_session_changed(self, index: int):
        data = self.session_combo.itemData(index)
        if not data:
            return
        session_mode, session_id = data
        self.session_mode = session_mode
        self.selected_session_id = session_id
        self.session_changed.emit(session_mode, session_id)
    
    def pick_color(self, status: str):
        current_color = QColor(self.status_colors.get(status, "#8E8E93"))
        color = QColorDialog.getColor(current_color, self, f"选择{status}颜色")
        
        if color.isValid():
            self.status_colors[status] = color.name()
            self.color_buttons[status].setStyleSheet(f"""
                QPushButton {{
                    background: {color.name()};
                    border: 1px solid rgba(255, 255, 255, 30);
                    border-radius: 6px;
                }}
            """)
    
    def apply_theme(self):
        theme_name = "dark" if self.theme_combo.currentIndex() == 0 else "light"
        self.theme_changed.emit(theme_name, self.status_colors, self.opacity_slider.value())
        self.accept()


# ============================================================
# Dynamic Island Widget - 修复字体颜色 + 智能缩进
# ============================================================
class DynamicIslandWidget(QWidget):
    clicked = pyqtSignal()
    mouse_entered = pyqtSignal()  # 鼠标进入信号
    mouse_left = pyqtSignal()     # 鼠标离开信号
    
    COMPACT_WIDTH = 360
    EXPANDED_WIDTH = 360
    COLLAPSED_WIDTH = 28
    PADDING = 36
    COLLAPSED_HEIGHT = 28  # 自动收拢后缩成圆球

    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.expanded = False
        self.collapsed = False  # 智能缩进状态
        self.detail_text = "Hermes 就绪"
        self.full_detail_text = self.detail_text
        self.status_name = "待机中"
        self.metadata = {}
        self.current_theme = Theme.DARK
        self.status_colors = DEFAULT_STATUS_COLORS.copy()
        self.theme_config = THEMES[self.current_theme]

        self.setObjectName("dynamicIsland")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)
        
        # 鼠标跟踪
        self.setMouseTracking(True)
        
        self.apply_theme()
        self.setup_ui()

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(18, 12, 18, 12)
        self.main_layout.setSpacing(6)

        # 顶行
        self.top_row = QHBoxLayout()
        self.top_row.setContentsMargins(0, 0, 0, 0)
        self.top_row.setSpacing(10)

        self.status_dot = StatusDot()
        self.top_row.addWidget(self.status_dot, alignment=Qt.AlignVCenter)

        self.detail_label = QLabel(self.detail_text)
        detail_font = QFont("PingFang SC", 13)
        detail_font.setWeight(QFont.Medium)
        self.detail_label.setFont(detail_font)
        self.detail_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.detail_label.setWordWrap(False)
        self.detail_label.setFixedHeight(24)
        self.top_row.addWidget(self.detail_label, 1)

        self.chevron_label = QLabel("⌄")
        chevron_font = QFont("PingFang SC", 14)
        self.chevron_label.setFont(chevron_font)
        self.chevron_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.top_row.addWidget(self.chevron_label, alignment=Qt.AlignVCenter)

        self.main_layout.addLayout(self.top_row)

        # 元信息
        self.meta_label = QLabel()
        meta_font = QFont("PingFang SC", 11)
        self.meta_label.setFont(meta_font)
        self.meta_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.meta_label.setWordWrap(True)
        self.meta_label.hide()
        self.main_layout.addWidget(self.meta_label)

        # 确保样式应用到所有 label
        self.apply_theme()
        
        self.set_status("waiting", self.detail_text)

    def apply_theme(self):
        self.theme_config = THEMES[self.current_theme]
        text_color = self.theme_config.text_color
        text_secondary = self.theme_config.text_secondary
        
        # 动态 border-radius: 保证即使展开也不会变方形
        height = self.height()
        radius = min(26, max(10, int(height * 0.38)))
        self.setStyleSheet(f"""
            QWidget#dynamicIsland {{
                background-color: {self.theme_config.bg_color};
                border: 1px solid {self.theme_config.border_color};
                border-radius: {radius}px;
            }}
            QLabel {{
                background: transparent;
                color: {text_color};
            }}
        """)
        
        # 强制设置每个 label 的颜色
        if hasattr(self, 'detail_label'):
            self.detail_label.setStyleSheet(f"color: {text_color}; background: transparent;")
        if hasattr(self, 'chevron_label'):
            self.chevron_label.setStyleSheet(f"color: {text_secondary}; background: transparent;")
        if hasattr(self, 'meta_label'):
            self.meta_label.setStyleSheet(f"color: {text_secondary}; background: transparent;")
    
    def set_theme(self, theme: str, status_colors: Dict):
        self.current_theme = Theme(theme)
        self.status_colors = status_colors
        self.apply_theme()
        if hasattr(self, 'current_status'):
            self.set_status(self.current_status, self.detail_text, self.metadata)

    def calculate_size(self, expanded: bool) -> QSize:
        base_width = self.EXPANDED_WIDTH if expanded else self.COMPACT_WIDTH
        
        if self.collapsed:
            return QSize(self.COLLAPSED_WIDTH, self.COLLAPSED_HEIGHT)
        
        if not expanded:
            return QSize(base_width, 52)
        
        # 展开时，计算所有内容的实际高度
        # 基础高度：顶行（状态点+详情+箭头）
        base_height = 52
        
        # 计算 detail_label 的实际高度（如果需要换行）
        detail_fm = QFontMetrics(self.detail_label.font())
        detail_rect = detail_fm.boundingRect(
            0, 0, base_width - self.PADDING - 30, 500,
            Qt.TextWordWrap,
            self.detail_text
        )
        detail_height = detail_rect.height() + 16
        
        # 计算 meta_label 的实际高度
        meta_height = 0
        if self.meta_label.text():
            meta_fm = QFontMetrics(self.meta_label.font())
            meta_rect = meta_fm.boundingRect(
                0, 0, base_width - self.PADDING, 500,
                Qt.TextWordWrap,
                self.meta_label.text()
            )
            meta_height = meta_rect.height() + 20  # 额外间距
        
        # 总高度 = 顶行 + 详情（如果换行）+ meta + padding
        total_height = max(base_height, detail_height) + meta_height + 12
        
        return QSize(base_width, total_height)

    def set_expanded(self, expanded: bool):
        self.expanded = expanded
        self.chevron_label.setText("⌃" if expanded else "⌢")
        
        if expanded and self.metadata:
            meta_text = self._format_metadata()
            self.meta_label.setText(meta_text)
            self.meta_label.show()
            self.meta_label.adjustSize()
        else:
            self.meta_label.hide()
        
        self.updateGeometry()
        self.adjustSize()
        
        if self.parent():
            size = self.calculate_size(expanded)
            self.parent().resize_for_content(size)
        self._update_detail_label()
        self.apply_theme()

    def set_collapsed(self, collapsed: bool):
        """设置自动收拢状态"""
        self.collapsed = collapsed
        if collapsed:
            self.main_layout.setContentsMargins(0, 0, 0, 0)
            self.main_layout.setSpacing(0)
            self.top_row.setContentsMargins(0, 0, 0, 0)
            self.top_row.setSpacing(0)
            self.detail_label.hide()
            self.chevron_label.hide()
            self.meta_label.hide()
            self.status_dot.show()
            self.status_dot.setFixedSize(14, 14)
        else:
            self.main_layout.setContentsMargins(18, 12, 18, 12)
            self.main_layout.setSpacing(6)
            self.top_row.setContentsMargins(0, 0, 0, 0)
            self.top_row.setSpacing(10)
            self.detail_label.show()
            self.chevron_label.show()
            self.status_dot.show()
            self.status_dot.setFixedSize(12, 12)
            if self.expanded:
                self.meta_label.show()

        if self.parent():
            size = self.calculate_size(self.expanded)
            self.parent().resize_for_content(size)
        self._update_detail_label()
        self.apply_theme()

    def enterEvent(self, event):
        """鼠标进入事件"""
        self.mouse_entered.emit()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """鼠标离开事件"""
        self.mouse_left.emit()
        super().leaveEvent(event)

    def _format_metadata(self) -> str:
        parts = []

        # 动作
        recent_activity = self.metadata.get('recent_activity') or []
        if recent_activity:
            parts.append(f"⚡ {self._clip_text(recent_activity[-1], 40)}")

        # 涉及文件
        recent_files = self.metadata.get('recent_files') or []
        if recent_files:
            filenames = []
            for item in recent_files[:3]:
                try:
                    filenames.append(Path(str(item)).name or str(item))
                except Exception:
                    filenames.append(str(item))
            parts.append(f"📁 {', '.join(filenames)}")

        # 任务
        if self.metadata.get('cron_name'):
            parts.append(f"⏱ {self.metadata['cron_name']}")

        # 下次运行
        if self.metadata.get('cron_next_run_at'):
            parts.append(f"🕐 下次 {self._format_clock_value(self.metadata['cron_next_run_at'])}")

        # 最近结果
        if self.metadata.get('cron_last_status') and self.metadata.get('cron_configured'):
            parts.append(f"📊 最近 {self.metadata['cron_last_status']}")

        # 错误
        if self.metadata.get('cron_last_error'):
            parts.append(f"❌ 任务错误: {self._clip_text(self.metadata['cron_last_error'], 36)}")
        if self.metadata.get('cron_last_delivery_error'):
            parts.append(f"⚠️ 回传错误: {self._clip_text(self.metadata['cron_last_delivery_error'], 36)}")

        # 模型
        if 'model' in self.metadata:
            parts.append(f"🤖 {self.metadata['model']}")

        # 阶段
        collaboration_stage = self._derive_collaboration_stage()
        if collaboration_stage:
            parts.append(f"📍 {collaboration_stage}")

        # 当前会话
        if self.metadata.get('resolved_session_id'):
            rsid = str(self.metadata['resolved_session_id'])
            if len(rsid) > 16:
                rsid = rsid[:8] + "..." + rsid[-4:]
            parts.append(f"💬 {rsid}")

        return "\n".join(parts) if parts else ""

    def _derive_collaboration_stage(self) -> str:
        status = getattr(self, 'current_status', '')
        metadata = self.metadata or {}
        recent_activity = metadata.get('recent_activity') or []
        latest = str(recent_activity[-1]) if recent_activity else ''
        lowered = latest.lower()

        if metadata.get('cron_configured') and status in ('waiting', 'idle'):
            if metadata.get('cron_last_status') == 'ok':
                return '定时待命'
            return '等待下一轮'

        if any(token in lowered for token in ('派发子任务', 'delegate_task')):
            return '执行器协作中'

        if any(token in latest for token in ('测试', '验证', '读取', '检索', '复核', '归档', '落档', '状态', '记录')) or any(token in lowered for token in ('skill', 'plan', 'grep', 'read', 'shell')):
            return '主控处理中'

        if any(token in latest for token in ('更新', '修复', '改', '补')) or any(token in lowered for token in ('edit', 'write', 'patch')):
            return '代码/记录修改中'

        if status in ('working', 'thinking'):
            return '处理中'
        if status in ('success',):
            return '已完成'
        return ''

    def _session_source_summary(self) -> str:
        has_db = self.metadata.get('session_exists_in_db')
        has_json = self.metadata.get('session_json_exists')
        if has_db and has_json:
            return 'DB + Live JSON'
        if has_db:
            return '仅 DB'
        if has_json:
            return '仅 Live JSON'
        return ''

    def _format_clock_value(self, value) -> str:
        if value in (None, ""):
            return "—"
        text = str(value).strip()
        if not text:
            return "—"
        if text.endswith('Z'):
            text = text[:-1] + '+00:00'
        try:
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is not None:
                dt = dt.astimezone().replace(tzinfo=None)
            return dt.strftime('%H:%M')
        except Exception:
            return text[:5] if len(text) >= 5 else text

    def _clip_text(self, value, limit: int = 48) -> str:
        text = (str(value) if value is not None else "").strip().replace("\n", " ")
        text = re.sub(r'\s+', ' ', text)
        if len(text) <= limit:
            return text
        return text[: limit - 1] + "…"

    def _update_detail_label(self):
        compact_mode = not self.expanded or self.collapsed
        detail = (self.full_detail_text or "").replace("\n", " ")
        if compact_mode:
            self.detail_label.setWordWrap(False)
            self.detail_label.setFixedHeight(24)
            available_width = max(80, self.width() - 84)
            elided = QFontMetrics(self.detail_label.font()).elidedText(detail, Qt.ElideRight, available_width)
            self.detail_label.setText(elided)
        else:
            self.detail_label.setWordWrap(len(detail) > 50)
            self.detail_label.setFixedHeight(max(24, self.detail_label.sizeHint().height()))
            self.detail_label.setText(self.full_detail_text)

    def set_status(self, status: str, detail: str, metadata: dict = None):
        self.current_status = status
        self.full_detail_text = detail or ""
        self.detail_text = self.full_detail_text
        self.metadata = metadata or {}
        self._update_detail_label()
        
        color = self.status_colors.get(status, "#8E8E93")
        pulsing = status in ("thinking", "working")
        
        self.status_dot.set_color(color)
        self.status_dot.set_pulsing(pulsing)
        
        if self.expanded:
            meta_text = self._format_metadata()
            self.meta_label.setText(meta_text)
            # 调整大小以适应新内容
            self.updateGeometry()
            self.adjustSize()
            if self.parent():
                size = self.calculate_size(self.expanded)
                self.parent().resize_for_content(size)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_detail_label()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        elif event.button() == Qt.RightButton:
            event.ignore()


# ============================================================
# 主窗口 - 智能缩进版
# ============================================================
class HermesDesktopPet(QWidget):
    STATUS_COLORS = DEFAULT_STATUS_COLORS.copy()
    WINDOW_WIDTH = DynamicIslandWidget.EXPANDED_WIDTH + 20
    
    def __init__(self):
        super().__init__()
        
        self.config = ConfigManager()
        
        self.expanded = False
        self.chat_mode = False
        self.history_mode = False
        self.performance_mode = False
        self.current_status = 'waiting'
        self.current_detail = ''
        self.send_worker = None
        self.manual_working_override: Optional[Dict] = None
        self._last_completion_signature = None
        self._last_completed_action = ""
        self._working_since = None
        
        self.instances = {DEFAULT_AGENT_SELECTION: DEFAULT_AGENT_LABEL}
        self.agent_options = []
        self.agent_info = {}
        self.current_instance = self.config.config.get("selected_agent", DEFAULT_AGENT_SELECTION)
        self.session_options: List[Dict] = []
        self.current_session_mode = self.config.config.get("session_mode", DEFAULT_SESSION_MODE)
        self.current_session_id = self.config.config.get("selected_session_id", DEFAULT_SESSION_AUTO)
        
        # 智能缩进相关
        self.auto_hide_enabled = self.config.config.get("auto_hide", True)
        self.auto_hide_timer = QTimer(self)
        self.auto_hide_timer.timeout.connect(self.auto_collapse)
        self.auto_hide_timeout = self.config.config.get("auto_hide_timeout", 5) * 1000
        self.is_collapsed = False
        self.last_uncollapsed_geometry = QRect(0, 0, self.WINDOW_WIDTH, 52)
        self.collapsed_edge = "right"
        self._last_auto_hide_signature = None

        # 最近动作面板开关
        self.activity_panel_visible = self.config.config.get("activity_panel_visible", True)
        
        # 展开动画
        self.expand_animation = None
        self.collapse_animation = None
        
        # 磁吸相关
        self.snap_threshold = 30
        self.is_dragging = False
        self.drag_position = None
        self.is_snapped = False
        
        self.setup_window()
        self.setup_ui()
        self.refresh_agent_options(notify=False)
        self.refresh_session_options(notify=False)
        self.init_monitor()
        self.init_tray()
        self.refresh_monitor_views()
        self.apply_requested_auto_hide_timeout(10)

        self.reset_auto_hide_timer()
    
    def setup_window(self):
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool |
            Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        if sys.platform == "darwin" and hasattr(Qt, "WA_MacAlwaysShowToolWindow"):
            self.setAttribute(Qt.WA_MacAlwaysShowToolWindow, True)
        
        self.setMinimumWidth(DynamicIslandWidget.COLLAPSED_WIDTH + 20)
        self.setMaximumWidth(self.WINDOW_WIDTH)
        self.resize(self.WINDOW_WIDTH, 52)
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)
        
        # 获取当前主题配置
        theme_name = self.config.config.get("theme", "dark")
        self.current_theme_config = THEMES[Theme(theme_name)]
        
        self.island = DynamicIslandWidget(self.config, self)
        self.island.clicked.connect(self.on_island_clicked)
        self.island.mouse_entered.connect(self.on_mouse_enter)
        self.island.mouse_left.connect(self.on_mouse_leave)
        layout.addWidget(self.island)

        self.content_scroll = QScrollArea(self)
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setFrameShape(QFrame.NoFrame)
        self.content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content_scroll.setStyleSheet("background: transparent;")
        self.content_scroll.hide()
        layout.addWidget(self.content_scroll)

        self.content_container = QWidget()
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(8)
        self.content_scroll.setWidget(self.content_container)

        self.activity_panel = ActivityPanel(self.content_container, self.current_theme_config)
        self.activity_panel.hide()
        self.content_layout.addWidget(self.activity_panel)

        self.history_panel = HistoryPanel(self.content_container, self.current_theme_config)
        self.history_panel.message_clicked.connect(self.on_history_message_clicked)
        self.history_panel.hide()
        self.content_layout.addWidget(self.history_panel)
        
        self.performance_panel = PerformancePanel(self.content_container, self.current_theme_config)
        self.performance_panel.hide()
        self.content_layout.addWidget(self.performance_panel)
        self.content_layout.addStretch()
        
        self.chat_input = ChatInput(self, self.current_theme_config)
        self.chat_input.message_sent.connect(self.send_to_hermes)
        self.chat_input.set_status_text("就绪")
        self.chat_input.hide()
        layout.addWidget(self.chat_input)
        
        self.opacity_effect = QGraphicsOpacityEffect(self.island)
        self.opacity_effect.setOpacity(1.0)
        self.island.setGraphicsEffect(self.opacity_effect)
        
        self.reposition()
        self.setWindowOpacity(self.config.config.get("opacity", 95) / 100.0)
        QTimer.singleShot(0, self.apply_platform_window_behavior)
        self.update_auxiliary_visibility()
    
    def resize_for_content(self, island_size: QSize):
        total_height = island_size.height() + 12

        if self.content_scroll.isVisible():
            self.content_container.adjustSize()
            scroll_height = min(max(120, self.content_container.sizeHint().height() + 6), 340)
            self.content_scroll.setFixedHeight(scroll_height)
            total_height += scroll_height
        else:
            self.content_scroll.setFixedHeight(0)
        
        if self.chat_mode:
            total_height += self.chat_input.height()
        
        total_width = max(DynamicIslandWidget.COLLAPSED_WIDTH + 20, min(self.WINDOW_WIDTH, island_size.width() + 20))
        self.setFixedSize(total_width, total_height)
        self.reposition()

    def update_auxiliary_visibility(self):
        show_activity = self.expanded and not self.is_collapsed and self.activity_panel_visible
        self.activity_panel.setVisible(show_activity)
        self.history_panel.setVisible(self.history_mode and not self.is_collapsed)
        self.performance_panel.setVisible(self.performance_mode and not self.is_collapsed)

        any_visible = (show_activity or self.history_mode or self.performance_mode) and not self.is_collapsed
        self.content_scroll.setVisible(any_visible)

        if hasattr(self, "monitor") and (show_activity or self.history_mode):
            messages = self.monitor.get_recent_history(10)
            self.activity_panel.update_events(messages)
            if self.history_mode:
                self.history_panel.update_history(messages[-5:])

        if hasattr(self, "monitor") and self.performance_mode:
            self.performance_panel.update_stats(self.monitor.performance.copy())

    def toggle_activity_panel(self):
        self.activity_panel_visible = not self.activity_panel_visible
        self.config.config["activity_panel_visible"] = self.activity_panel_visible
        self.config.save_config()
        self.update_auxiliary_visibility()
    
    def reposition(self):
        screen = QApplication.primaryScreen().geometry()
        x = screen.x() + (screen.width() - self.width()) // 2
        
        if self.is_snapped:
            return
        
        y = screen.y() + 6
        self.move(x, y)
    
    def toggle_expanded(self):
        self.expanded = not self.expanded
        self.island.set_expanded(self.expanded)
        self.update_auxiliary_visibility()
        current_size = self.island.calculate_size(self.expanded)
        self.resize_for_content(current_size)
        self.reset_auto_hide_timer()
    
    def on_island_clicked(self):
        """点击切换详情展开；收拢成圆球时只允许 hover 恢复"""
        if self.is_collapsed:
            self.reset_auto_hide_timer()
            return
        self.toggle_expanded()
        self.reset_auto_hide_timer()
    
    # ============================================================
    # 智能缩进功能
    # ============================================================
    def on_mouse_enter(self):
        """鼠标进入岛屿/圆球区域"""
        try:
            if self.is_collapsed:
                self.expand_from_collapsed()
            self.reset_auto_hide_timer()
        except Exception as e:
            print(f"on_mouse_enter failed: {e}", file=sys.stderr)

    def on_mouse_leave(self):
        """鼠标离开岛屿区域"""
        self.reset_auto_hide_timer()

    def _load_cron_jobs_for_menu(self) -> List[Dict[str, Any]]:
        if hasattr(self, "monitor") and hasattr(self.monitor, "_load_cron_jobs"):
            try:
                return self.monitor._load_cron_jobs()
            except Exception:
                return []
        return []

    def _save_cron_jobs_for_menu(self, jobs: List[Dict[str, Any]]) -> bool:
        cron_path = getattr(getattr(self, "monitor", None), "cron_jobs_path", None)
        if not cron_path:
            return False
        try:
            payload = {"jobs": jobs, "updated_at": datetime.now().astimezone().isoformat()}
            Path(cron_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2))
            return True
        except Exception:
            return False

    def set_cron_job_enabled(self, job_id: str, enabled: bool):
        jobs = self._load_cron_jobs_for_menu()
        changed = False
        for job in jobs:
            if str(job.get("id") or job.get("job_id") or "") == str(job_id):
                job["enabled"] = bool(enabled)
                job["state"] = "scheduled" if enabled else "paused"
                if enabled:
                    job["paused_at"] = None
                    job["paused_reason"] = None
                else:
                    job["paused_at"] = datetime.now().astimezone().isoformat()
                    job["paused_reason"] = "desktop-pet-toggle"
                changed = True
                break
        if not changed:
            send_macos_notification("Hermes", "未找到要切换的定时任务")
            return
        if self._save_cron_jobs_for_menu(jobs):
            action = "启用" if enabled else "停用"
            send_macos_notification("Hermes", f"已{action}定时任务: {job_id}")
            self.refresh_monitor_views()
        else:
            send_macos_notification("Hermes", f"切换定时任务失败: {job_id}")

    def _populate_cron_menu(self, parent_menu: QMenu):
        jobs = self._load_cron_jobs_for_menu()
        if not jobs:
            empty_action = QAction("暂无定时任务", self)
            empty_action.setEnabled(False)
            parent_menu.addAction(empty_action)
            return
        for job in jobs:
            name = str(job.get("name") or job.get("id") or "未命名任务")
            state = str(job.get("last_status") or job.get("state") or "unknown")
            sub = parent_menu.addMenu(f"{name} · {state}")
            info_action = QAction(f"下次: {self.monitor._safe_iso_display(job.get('next_run_at')) if hasattr(self, 'monitor') else '—'}", self)
            info_action.setEnabled(False)
            sub.addAction(info_action)
            enabled_action = QAction("启用", self)
            enabled_action.setCheckable(True)
            enabled_action.setChecked(bool(job.get("enabled", True)))
            job_id = str(job.get("id") or job.get("job_id") or "")
            enabled_action.triggered.connect(lambda checked, jid=job_id: self.set_cron_job_enabled(jid, checked))
            sub.addAction(enabled_action)
            trigger_action = QAction("⚡ 立即触发", self)
            trigger_action.triggered.connect(lambda checked, jid=job_id: self.trigger_cron_now(jid))
            sub.addAction(trigger_action)

    def trigger_cron_now(self, job_id: str):
        if not job_id:
            send_macos_notification("Hermes", "未指定任务 ID")
            return
        try:
            result = subprocess.run(
                ["hermes", "cron", "run", job_id],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                send_macos_notification("Hermes", f"已触发: {job_id}")
            else:
                send_macos_notification("Hermes", f"触发失败: {(result.stderr or result.stdout or '').strip()[:80]}")
        except Exception as e:
            send_macos_notification("Hermes", f"触发异常: {e}")
    
    def auto_collapse(self):
        """10 秒未悬停时自动收拢成圆球"""
        if not self.auto_hide_enabled:
            return
        if self.is_collapsed:
            return
        if self.is_dragging or self.chat_mode or self.history_mode or self.performance_mode:
            return
        self.collapse_to_edge()
    
    def _build_collapsed_geometry(self) -> QRect:
        current = self.last_uncollapsed_geometry if self.last_uncollapsed_geometry.width() > 0 else self.geometry()
        orb_size = DynamicIslandWidget.COLLAPSED_WIDTH + 20
        target_x = current.x() + (current.width() - orb_size) // 2
        target_y = current.y() + (current.height() - orb_size) // 2
        return QRect(target_x, target_y, orb_size, orb_size)
    
    def collapse_to_edge(self):
        """收拢为仅保留状态灯的圆球"""
        if self.is_collapsed:
            return
        self.last_uncollapsed_geometry = self.geometry()
        self.is_collapsed = True
        self.island.set_collapsed(True)
        self.update_auxiliary_visibility()
        self._collapse_anim = QPropertyAnimation(self, b"geometry")
        self._collapse_anim.setDuration(1000)
        self._collapse_anim.setStartValue(self.geometry())
        self._collapse_anim.setEndValue(self._build_collapsed_geometry())
        self._collapse_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._collapse_anim.start()
    
    def expand_from_collapsed(self, emphasize: bool = False):
        """从圆球平滑恢复到灵动岛"""
        if not self.is_collapsed:
            return
        target = self.last_uncollapsed_geometry if self.last_uncollapsed_geometry.width() > 0 else QRect(self.x(), self.y(), self.WINDOW_WIDTH, 52)
        self.is_collapsed = False
        self.expanded = False
        self.island.set_collapsed(False)
        self.island.set_expanded(False)
        self.update_auxiliary_visibility()
        self._expand_anim = QPropertyAnimation(self, b"geometry")
        self._expand_anim.setDuration(1000)
        self._expand_anim.setStartValue(self.geometry())
        self._expand_anim.setEndValue(target)
        self._expand_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._expand_anim.start()
        if emphasize:
            self.animate_status_change()
    
    # ============================================================
    # 聊天功能
    # ============================================================
    def toggle_chat(self):
        self.chat_mode = not self.chat_mode
        
        if self.chat_mode:
            self.chat_input.show()
            QTimer.singleShot(100, self.chat_input.focus_input)
        else:
            self.chat_input.hide()
        
        current_size = self.island.calculate_size(self.expanded)
        self.resize_for_content(current_size)
        self.reset_auto_hide_timer()
    
    def send_to_hermes(self, message: str):
        history = self.config.load_history()
        history.append({
            "role": "user",
            "content": message,
            "timestamp": datetime.now().isoformat()
        })
        self.config.save_history(history)
        if self.send_worker and self.send_worker.isRunning():
            self.chat_input.set_status_text("上一次发送仍在进行中", error=True)
            return

        session_id = ""
        if isinstance(self.island.metadata, dict):
            session_id = (
                self.island.metadata.get("resolved_session_id")
                or self.island.metadata.get("session_id", "")
            )
        self.chat_input.set_busy(True)
        self.chat_input.set_status_text("发送中...", error=False)
        self.manual_working_override = {
            "detail": "已发送，等待 Hermes 响应...",
            "started_at": time.time(),
            "message": message,
        }
        self.on_status_changed(
            'working',
            self.manual_working_override["detail"],
            {
                "status": "working",
                "status_reason": "manual_send_override",
                "manual_working_override": True,
                "selected_agent": self.current_instance,
            },
        )
        self.send_worker = HermesSendWorker(message, self.current_instance, session_id, self)
        self.send_worker.completed.connect(self.on_send_completed)
        self.send_worker.start()
    
    def send_quick_message(self, message: str):
        self.send_to_hermes(message)
    
    # ============================================================
    # 历史消息
    # ============================================================
    def toggle_history(self):
        self.history_mode = not self.history_mode
        
        if self.history_mode:
            messages = self.monitor.get_recent_history(5)
            self.history_panel.update_history(messages)
        self.update_auxiliary_visibility()
        current_size = self.island.calculate_size(self.expanded)
        self.resize_for_content(current_size)
    
    def on_history_message_clicked(self, content: str):
        send_macos_notification("消息详情", content[:200])
    
    # ============================================================
    # 性能仪表板
    # ============================================================
    def toggle_performance(self):
        self.performance_mode = not self.performance_mode
        self.update_auxiliary_visibility()
        current_size = self.island.calculate_size(self.expanded)
        self.resize_for_content(current_size)
    
    # ============================================================
    # 监控和通知
    # ============================================================
    def init_monitor(self):
        self.monitor = HermesMonitor(
            self.current_instance,
            self.current_session_mode,
            self.current_session_id,
        )
        self.monitor.status_changed.connect(self.on_status_changed)
        self.monitor.task_completed.connect(self.on_task_completed)
        self.monitor.history_updated.connect(self.history_panel.update_history)
        self.monitor.history_updated.connect(self.activity_panel.update_events)
        self.monitor.performance_updated.connect(self.performance_panel.update_stats)
        self.monitor.start()

    def _derive_live_headline(self, status: str, detail: str, metadata: Dict[str, Any]) -> str:
        metadata = metadata or {}
        if metadata.get('status_reason') == 'runtime_live_activity' and metadata.get('live_detail'):
            return str(metadata.get('live_detail'))
        if status not in ('working', 'thinking'):
            return detail

        try:
            recent = self.monitor.get_recent_history(1) if hasattr(self, 'monitor') else []
        except Exception:
            recent = []

        if recent:
            try:
                headline = self.monitor._top_detail_from_activity(recent[-1], status)
                if headline and headline not in ('正在处理...', '处理中...', '处理中'):
                    return headline
            except Exception:
                pass

        recent_files = metadata.get('recent_files') or []
        if recent_files:
            try:
                names = [Path(str(item)).name or str(item) for item in recent_files[:2]]
            except Exception:
                names = [str(item) for item in recent_files[:2]]
            return f"正在处理文件: {', '.join(names)}"[:64]

        recent_activity = metadata.get('recent_activity') or []
        if recent_activity:
            latest = str(recent_activity[-1]).strip()
            latest = re.sub(r'^[^\w\u4e00-\u9fff]+', '', latest)
            latest = latest.replace('read ', '正在读取 ')
            latest = latest.replace('grep ', '正在检索 ')
            latest = latest.replace('shell ', '正在执行 shell ')
            latest = latest.replace('write ', '正在写入 ')
            latest = latest.replace('edit ', '正在修改 ')
            if latest:
                return latest[:64]

        return detail
    
    def on_status_changed(self, status: str, detail: str, metadata: dict):
        metadata = metadata or {}
        if self.manual_working_override:
            if status in ('working', 'thinking', 'error'):
                self.manual_working_override = None
            else:
                status = 'working'
                detail = self.manual_working_override.get("detail", "已发送，等待 Hermes 响应...")
                metadata = {
                    **metadata,
                    "status": "working",
                    "status_reason": "manual_send_override",
                    "manual_working_override": True,
                    "selected_agent": self.current_instance,
                }

        old_status = self.current_status
        previous_detail = self.current_detail
        self.current_status = status

        # 完成摘要：刚做完什么
        if old_status in ('working', 'thinking') and status in ('waiting', 'idle'):
            meaningful = previous_detail.strip()
            meaningful = SYSTEM_COMPLETION_LABELS.get(meaningful, meaningful)
            if meaningful and meaningful not in TRANSIENT_COMPLETION_TEXTS and meaningful not in ('等待指令', '处理中', '正在处理', 'Hermes 就绪'):
                self._last_completed_action = meaningful
        elif status in ('working', 'thinking'):
            self._last_completed_action = ""

        recent_activity = metadata.get("recent_activity") or []
        if detail in ("正在处理...", "处理中...", "处理中", "等待指令") and recent_activity:
            latest_activity = self.monitor._activity_core(recent_activity[-1]) if hasattr(self, 'monitor') else str(recent_activity[-1])
            if latest_activity:
                detail = latest_activity[:64]
        elif detail in ("正在处理...", "处理中...", "处理中", "等待指令"):
            recent_files = metadata.get("recent_files") or []
            if recent_files:
                try:
                    names = [Path(str(item)).name or str(item) for item in recent_files[:2]]
                except Exception:
                    names = [str(item) for item in recent_files[:2]]
                detail = f"关注文件: {', '.join(names)}"[:64]
            elif metadata.get("session_fallback_reason"):
                detail = f"状态回退: {str(metadata['session_fallback_reason'])[:48]}"

        detail = self._derive_live_headline(status, detail, metadata)

        # 待命时显示刚完成的摘要
        if status in ('waiting', 'idle') and self._last_completed_action:
            detail = f"刚完成: {self._last_completed_action[:52]}"

        # 卡住检测
        if status == 'working':
            if old_status != 'working' or self._working_since is None:
                self._working_since = time.time()
            else:
                elapsed = time.time() - self._working_since
                live_age = metadata.get('live_age_seconds')
                if elapsed > 60 and (live_age is None or live_age > 25):
                    detail = f"⚠️ 疑似卡住 · {int(elapsed)}s 无实质进展"
        else:
            self._working_since = None

        self.monitor._append_pet_debug_log(status, detail, metadata) if hasattr(self, 'monitor') else None

        self.current_detail = detail
        
        self.island.set_status(status, detail, metadata)
        if hasattr(self, 'tray_icon'):
            self.tray_icon.setIcon(self._build_tray_icon(status))
            self.tray_icon.setToolTip(self._build_tray_tooltip(status, detail, metadata))
        if self.expanded and isinstance(metadata, dict) and metadata.get("recent_activity") and not self.activity_panel.events:
            self.activity_panel.update_events(self.monitor.get_recent_history(10))
        
        if old_status != status:
            self.animate_status_change()
            
            if status == 'working' and old_status != 'working':
                play_sound("Tink")

        completion_signature = (
            metadata.get('cron_last_run_at'),
            metadata.get('cron_last_status'),
            detail,
        )
        if status in ('waiting', 'idle', 'success') and metadata.get('cron_last_status') == 'ok':
            if completion_signature != self._last_completion_signature:
                self._last_completion_signature = completion_signature
                notify_lines = []
                if metadata.get('cron_name'):
                    notify_lines.append(str(metadata['cron_name']))
                notify_lines.append(detail[:120] if detail else '自动推进已完成')
                if metadata.get('cron_next_run_at'):
                    notify_lines.append(f"下次 {self.monitor._safe_iso_display(metadata['cron_next_run_at'])}")
                send_macos_notification('Hermes 自动推进完成', ' · '.join(notify_lines), sound=True)
        
        auto_hide_signature = (
            status,
            detail,
            metadata.get('status_reason'),
            tuple((metadata.get('recent_activity') or [])[-2:]),
            metadata.get('cron_last_run_at'),
            metadata.get('cron_last_status'),
        )
        if auto_hide_signature != self._last_auto_hide_signature or previous_detail != detail or old_status != status:
            self._last_auto_hide_signature = auto_hide_signature
            self.reset_auto_hide_timer()

    def on_send_completed(self, success: bool, stdout_text: str, stderr_text: str):
        self.chat_input.set_busy(False)
        response_text = stdout_text.strip()
        error_text = stderr_text.strip()

        if success:
            self.manual_working_override = None
            if response_text:
                history = self.config.load_history()
                history.append({
                    "role": "assistant",
                    "content": response_text,
                    "timestamp": datetime.now().isoformat()
                })
                self.config.save_history(history)
            summary = response_text[:80] if response_text else "消息已发送并完成处理"
            self.chat_input.set_status_text(summary, error=False)
            play_sound("Glass")
            send_macos_notification("Hermes", summary)
            self.refresh_monitor_views()
            QTimer.singleShot(800, self.refresh_monitor_views)
        else:
            self.manual_working_override = None
            detail = error_text or response_text or "Hermes CLI 调用失败"
            self.chat_input.set_status_text(f"发送失败: {detail[:120]}", error=True)
            send_macos_notification("Hermes", f"发送失败: {detail[:160]}")
            self.on_status_changed(
                'error',
                f"发送失败: {detail[:80]}",
                {
                    "status": "error",
                    "status_reason": "send_failed",
                    "manual_working_override": False,
                    "selected_agent": self.current_instance,
                },
            )
            self.refresh_monitor_views()

    def refresh_monitor_views(self):
        if not hasattr(self, "monitor"):
            return
        try:
            status, detail, metadata = self.monitor.get_status_snapshot()
            self.on_status_changed(status, detail, metadata)
        except Exception:
            pass

        messages = self.monitor.get_recent_history(10)
        self.activity_panel.update_events(messages)
        if self.history_mode:
            self.history_panel.update_history(messages[-5:])
        if self.performance_mode:
            self.performance_panel.update_stats(self.monitor.performance.copy())
    
    def on_task_completed(self, detail: str):
        send_macos_notification(
            "Hermes 任务完成",
            detail[:100] if detail else "任务已完成",
            sound=True
        )
        play_sound("Glass")
    
    def animate_status_change(self):
        if hasattr(self, '_status_anim'):
            self._status_anim.stop()
        
        self._status_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self._status_anim.setDuration(300)
        self._status_anim.setStartValue(0.85)
        self._status_anim.setEndValue(1.0)
        self._status_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._status_anim.start()
    
    # ============================================================
    # 右键菜单和快捷操作
    # ============================================================
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: rgba(30, 30, 35, 245);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 8px 24px;
                border-radius: 4px;
                color: rgba(255, 255, 255, 220);
            }
            QMenu::item:selected {
                background: rgba(48, 209, 88, 60);
            }
            QMenu::separator {
                height: 1px;
                background: rgba(255, 255, 255, 20);
                margin: 4px 8px;
            }
        """)
        
        chat_action = QAction("💬 发送消息", self)
        chat_action.triggered.connect(self.toggle_chat)
        menu.addAction(chat_action)
        
        menu.addSeparator()
        
        quick_menu = menu.addMenu("⚡ 快捷消息")
        quick_messages = self.config.config.get("quick_messages", QUICK_MESSAGES)
        for msg in quick_messages:
            action = QAction(msg, self)
            action.triggered.connect(lambda checked, m=msg: self.send_quick_message(m))
            quick_menu.addAction(action)
        
        menu.addSeparator()
        
        history_action = QAction("📜 最近消息", self)
        history_action.triggered.connect(self.toggle_history)
        menu.addAction(history_action)

        activity_action = QAction("📡 最近动作", self)
        activity_action.setCheckable(True)
        activity_action.setChecked(self.activity_panel_visible)
        activity_action.triggered.connect(self.toggle_activity_panel)
        menu.addAction(activity_action)
        
        performance_action = QAction("📊 性能统计", self)
        performance_action.triggered.connect(self.toggle_performance)
        menu.addAction(performance_action)
        
        menu.addSeparator()

        cron_menu = menu.addMenu("⏱ 定时任务")
        self._populate_cron_menu(cron_menu)
        
        menu.addSeparator()
        
        restart_action = QAction("🔄 重启网关", self)
        restart_action.triggered.connect(self.restart_gateway)
        menu.addAction(restart_action)
        
        logs_action = QAction("📋 查看日志", self)
        logs_action.triggered.connect(self.open_logs)
        menu.addAction(logs_action)
        
        status_action = QAction("当前状态", self)
        status_action.triggered.connect(self.show_status)
        menu.addAction(status_action)
        
        menu.addSeparator()
        
        theme_action = QAction("🎨 主题与 Agent", self)
        theme_action.triggered.connect(self.show_theme_dialog)
        menu.addAction(theme_action)
        
        if len(self.instances) > 1:
            instance_menu = menu.addMenu("🔗 Agent 切换")
            for inst_id, inst_name in self.instances.items():
                action = QAction(inst_name, self)
                action.setCheckable(True)
                action.setChecked(inst_id == self.current_instance)
                action.triggered.connect(lambda checked, i=inst_id: self.switch_instance(i))
                instance_menu.addAction(action)
        
        menu.addSeparator()
        
        auto_hide_action = QAction("🫧 自动收拢", self)
        auto_hide_action.setCheckable(True)
        auto_hide_action.setChecked(self.auto_hide_enabled)
        auto_hide_action.triggered.connect(self.toggle_auto_hide)
        menu.addAction(auto_hide_action)
        
        menu.addSeparator()
        
        toggle_action = QAction("👁 显示/隐藏", self)
        toggle_action.triggered.connect(self.toggle_visibility)
        menu.addAction(toggle_action)
        
        quit_action = QAction("🚪 退出", self)
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(quit_action)
        
        menu.exec_(event.globalPos())
        self.reset_auto_hide_timer()
    
    def restart_gateway(self):
        try:
            subprocess.Popen(["hermes", "gateway", "restart"])
            send_macos_notification("Hermes", "正在重启网关...")
            play_sound("Pop")
        except Exception as e:
            send_macos_notification("Hermes", f"重启失败: {e}")
    
    def open_logs(self):
        logs_dir = Path.home() / ".hermes" / "logs"
        if logs_dir.exists():
            subprocess.run(["open", str(logs_dir)])
        else:
            send_macos_notification("Hermes", "日志目录不存在")
    
    def show_status(self):
        info = f"状态: {self.current_status}\n详情: {self.current_detail}\nAgent: {self.current_instance}"
        send_macos_notification("Hermes 状态", info)
    
    def toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            if self.is_collapsed:
                self.expand_from_collapsed()
    
    # ============================================================
    # 主题设置
    # ============================================================
    def show_theme_dialog(self):
        current_theme = self.config.config.get("theme", "dark")
        status_colors = self.config.config.get("status_colors", DEFAULT_STATUS_COLORS)
        agent_options, agent_info = self.refresh_agent_options(notify=False)
        session_options, session_info = self.refresh_session_options(notify=False)
        
        dialog = ThemeDialog(
            current_theme,
            status_colors,
            self.config.config.get("opacity", 95),
            agent_options,
            self.current_instance,
            agent_info,
            session_options,
            session_info.get("session_mode", self.current_session_mode),
            session_info.get("selected_session_id", self.current_session_id),
            self,
        )
        dialog.theme_changed.connect(self.on_theme_changed)
        dialog.agent_changed.connect(self.switch_instance)
        dialog.session_changed.connect(self.switch_session)
        dialog.exec_()
    
    def on_theme_changed(self, theme: str, status_colors: Dict, opacity: int):
        self.config.config["theme"] = theme
        self.config.config["status_colors"] = status_colors
        self.config.config["opacity"] = opacity
        self.config.save_config()
        
        # 更新所有组件的主题
        self.current_theme_config = THEMES[Theme(theme)]
        self.island.set_theme(theme, status_colors)
        self.chat_input.update_theme(self.current_theme_config)
        self.history_panel.update_theme(self.current_theme_config)
        self.activity_panel.update_theme(self.current_theme_config)
        self.performance_panel.update_theme(self.current_theme_config)
        
        self.STATUS_COLORS = status_colors
        self.setWindowOpacity(opacity / 100.0)
        send_macos_notification("Hermes", "主题已更新")
    
    # ============================================================
    # 多实例支持
    # ============================================================
    def refresh_agent_options(self, notify: bool = False) -> Tuple[List[Dict], Dict]:
        probe = self.monitor if hasattr(self, "monitor") else HermesMonitor(self.current_instance)
        probe.set_selected_agent(self.current_instance)
        agent_options, agent_info = probe.get_available_agents()

        self.agent_options = agent_options
        self.agent_info = agent_info
        self.instances = {item["id"]: item["label"] for item in agent_options}

        available_ids = set(self.instances.keys())
        resolved_agent = agent_info.get("selected_agent", self.current_instance)
        if (
            resolved_agent == DEFAULT_AGENT_SELECTION
            and agent_info.get("field") == "agent_id"
            and len(agent_options) > 1
        ):
            resolved_agent = agent_options[1]["id"]
        if resolved_agent not in available_ids:
            resolved_agent = DEFAULT_AGENT_SELECTION

        if resolved_agent != self.current_instance:
            self.current_instance = resolved_agent
            self.config.config["selected_agent"] = resolved_agent
            self.config.config["instance_id"] = resolved_agent
            self.config.save_config()
            if notify:
                send_macos_notification("Hermes", "已刷新 agent 列表")

        if hasattr(self, "monitor"):
            self.monitor.set_selected_agent(self.current_instance)

        return agent_options, agent_info

    def refresh_session_options(self, notify: bool = False) -> Tuple[List[Dict], Dict]:
        probe = self.monitor if hasattr(self, "monitor") else HermesMonitor(
            self.current_instance,
            self.current_session_mode,
            self.current_session_id,
        )
        probe.set_selected_agent(self.current_instance)
        probe.set_session_selection(self.current_session_mode, self.current_session_id)
        session_options, session_info = probe.get_available_sessions()

        self.session_options = session_options
        resolved_mode = session_info.get("session_mode", self.current_session_mode)
        resolved_session_id = session_info.get("selected_session_id", self.current_session_id)
        self.current_session_mode = resolved_mode
        self.current_session_id = resolved_session_id
        self.config.config["session_mode"] = resolved_mode
        self.config.config["selected_session_id"] = resolved_session_id
        self.config.save_config()

        if hasattr(self, "monitor"):
            self.monitor.set_session_selection(self.current_session_mode, self.current_session_id)

        return session_options, session_info

    def switch_instance(self, instance_id: str):
        if not instance_id:
            return
        if instance_id == self.current_instance and hasattr(self, "monitor"):
            return

        self.current_instance = instance_id
        self.config.config["selected_agent"] = instance_id
        self.config.config["instance_id"] = instance_id
        self.current_session_mode = DEFAULT_SESSION_MODE
        self.current_session_id = DEFAULT_SESSION_AUTO
        self.config.config["session_mode"] = self.current_session_mode
        self.config.config["selected_session_id"] = self.current_session_id
        self.config.save_config()

        self.refresh_agent_options(notify=False)
        self.refresh_session_options(notify=False)

        if hasattr(self, "monitor"):
            self.monitor.stop()
            self.monitor.wait()
        self.init_monitor()
        self.update_auxiliary_visibility()
        self.refresh_monitor_views()

        if self.history_mode:
            self.history_panel.update_history(self.monitor.get_recent_history(5))
        if self.performance_mode:
            self.performance_panel.update_stats(self.monitor.performance.copy())
        
        agent_name = self.instances.get(instance_id, instance_id)
        send_macos_notification("Hermes", f"已切换到 Agent: {agent_name}")

    def apply_requested_auto_hide_timeout(self, seconds: int = 5):
        seconds = max(1, int(seconds))
        self.config.config["auto_hide_timeout"] = seconds
        self.config.save_config()
        self.auto_hide_timeout = seconds * 1000

    def switch_session(self, session_mode: str, session_id: str):
        self.current_session_mode = session_mode or DEFAULT_SESSION_MODE
        self.current_session_id = session_id or DEFAULT_SESSION_AUTO
        self.config.config["session_mode"] = self.current_session_mode
        self.config.config["selected_session_id"] = self.current_session_id
        self.config.save_config()

        if hasattr(self, "monitor"):
            self.monitor.set_session_selection(self.current_session_mode, self.current_session_id)
        self.refresh_session_options(notify=False)
        self.refresh_monitor_views()
    
    # ============================================================
    # 系统托盘
    # ============================================================
    def _build_tray_icon(self, status: str = "waiting") -> QIcon:
        color = QColor(self.STATUS_COLORS.get(status, DEFAULT_STATUS_COLORS.get(status, "#8E8E93")))
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(16, 16, 20))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(2, 6, 28, 20, 10, 10)
        p.setBrush(color)
        p.drawEllipse(6, 12, 7, 7)
        p.end()
        return QIcon(pixmap)

    def init_tray(self):
        tray_menu = QMenu()
        tray_menu.setStyleSheet("""
            QMenu {
                background: rgba(30, 30, 35, 245);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 8px;
            }
            QMenu::item {
                padding: 8px 20px;
                color: rgba(255, 255, 255, 220);
            }
            QMenu::item:selected {
                background: rgba(48, 209, 88, 60);
            }
        """)
        
        show_action = QAction("显示", self)
        show_action.triggered.connect(self.show)
        tray_menu.addAction(show_action)
        
        chat_action = QAction("发送消息", self)
        chat_action.triggered.connect(self.toggle_chat)
        tray_menu.addAction(chat_action)

        cron_menu = tray_menu.addMenu("⏱ 定时任务")
        self._populate_cron_menu(cron_menu)
        
        tray_menu.addSeparator()
        
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.quit_app)
        tray_menu.addAction(quit_action)
        
        self.tray_icon = QSystemTrayIcon(self._build_tray_icon(self.current_status), self)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.setToolTip("Hermes 灵动岛")
        self.tray_icon.show()

    def _build_tray_tooltip(self, status: str, detail: str, metadata: Dict[str, Any]) -> str:
        lines = [f"Hermes: {status}", detail or "等待指令"]
        if metadata.get("cron_name"):
            lines.append(f"任务: {metadata['cron_name']}")
        if metadata.get("cron_job_id"):
            lines.append(f"ID: {str(metadata['cron_job_id'])[:18]}")
        if metadata.get("cron_last_status"):
            lines.append(f"最近: {metadata['cron_last_status']}")
        if metadata.get("cron_next_run_at"):
            lines.append(f"下次: {self.monitor._safe_iso_display(metadata['cron_next_run_at'])}")
        if metadata.get("last_message_timestamp"):
            lines.append(f"最后: {self.monitor._safe_iso_display(metadata['last_message_timestamp'])}")

        source_bits = []
        if metadata.get("session_exists_in_db"):
            source_bits.append("DB")
        if metadata.get("session_json_exists"):
            source_bits.append("Live")
        if source_bits:
            lines.append(f"来源: {'+'.join(source_bits)}")
        elif metadata.get("session_fallback_reason"):
            lines.append(f"回退: {str(metadata['session_fallback_reason'])[:24]}")

        if hasattr(self, 'island') and hasattr(self.island, '_derive_collaboration_stage'):
            self.island.metadata = metadata or {}
            self.island.current_status = status
            stage = self.island._derive_collaboration_stage()
            if stage:
                lines.append(f"阶段: {stage}")

        recent_activity = metadata.get("recent_activity") or []
        if recent_activity:
            activity = self.monitor._activity_core(recent_activity[-1]) if hasattr(self.monitor, '_activity_core') else str(recent_activity[-1])
            if activity:
                lines.append(f"动作: {activity[:60]}")
        elif metadata.get("cron_last_error"):
            lines.append(f"任务错误: {str(metadata['cron_last_error'])[:60]}")
        elif metadata.get("cron_last_delivery_error"):
            lines.append(f"回传错误: {str(metadata['cron_last_delivery_error'])[:60]}")

        return "\n".join(lines[:7])
    
    # ============================================================
    # 智能缩进计时器
    # ============================================================
    def toggle_auto_hide(self, enabled: bool):
        self.auto_hide_enabled = enabled
        self.config.config["auto_hide"] = enabled
        self.config.save_config()
        
        if enabled:
            self.reset_auto_hide_timer()
        else:
            self.auto_hide_timer.stop()
    
    def reset_auto_hide_timer(self):
        if self.auto_hide_enabled:
            self.auto_hide_timer.stop()
            self.auto_hide_timer.start(self.auto_hide_timeout)
    
    # ============================================================
    # 磁吸边缘
    # ============================================================
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.is_dragging = True
            self.drag_position = event.globalPos() - self.pos()
            event.accept()
        else:
            super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event: QMouseEvent):
        if self.is_dragging and event.buttons() & Qt.LeftButton:
            new_pos = event.globalPos() - self.drag_position
            self.move(new_pos)
            self.is_snapped = False
            event.accept()
        else:
            super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and self.is_dragging:
            self.is_dragging = False
            self.check_snap_to_edge()
            self.reset_auto_hide_timer()
            event.accept()
        else:
            super().mouseReleaseEvent(event)
    
    def check_snap_to_edge(self):
        screen = QApplication.primaryScreen().geometry()
        pos = self.pos()
        size = self.size()
        
        if pos.x() < self.snap_threshold:
            self.animate_snap(QPoint(10, pos.y()))
            self.is_snapped = True
            return
        
        right_edge = screen.width() - pos.x() - size.width()
        if right_edge < self.snap_threshold:
            self.animate_snap(QPoint(screen.width() - size.width() - 10, pos.y()))
            self.is_snapped = True
            return
        
        if pos.y() < self.snap_threshold:
            self.animate_snap(QPoint(pos.x(), 6))
            self.is_snapped = True
            return
        
        bottom_edge = screen.height() - pos.y() - size.height()
        if bottom_edge < self.snap_threshold:
            self.animate_snap(QPoint(pos.x(), screen.height() - size.height() - 10))
            self.is_snapped = True
            return
    
    def animate_snap(self, target_pos: QPoint):
        self._snap_anim = QPropertyAnimation(self, b"pos")
        self._snap_anim.setDuration(200)
        self._snap_anim.setStartValue(self.pos())
        self._snap_anim.setEndValue(target_pos)
        self._snap_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._snap_anim.start()
    
    # ============================================================
    # 平台特定
    # ============================================================
    def apply_platform_window_behavior(self):
        if sys.platform != "darwin" or objc is None:
            return
        
        try:
            ns_view = objc.objc_object(c_void_p=int(self.winId()))
            ns_window = ns_view.window()
            if ns_window is None:
                return
            
            behavior = 0
            for flag in (
                NSWindowCollectionBehaviorCanJoinAllSpaces,
                NSWindowCollectionBehaviorStationary,
                NSWindowCollectionBehaviorFullScreenAuxiliary,
            ):
                if flag is not None:
                    behavior |= flag
            
            if behavior:
                ns_window.setCollectionBehavior_(behavior)
            
            if NSFloatingWindowLevel is not None:
                ns_window.setLevel_(NSFloatingWindowLevel)
            
            if hasattr(ns_window, "setHidesOnDeactivate_"):
                ns_window.setHidesOnDeactivate_(False)
        
        except Exception as e:
            print(f"macOS 窗口设置失败: {e}", file=sys.stderr)
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            if self.chat_mode:
                self.toggle_chat()
            elif self.history_mode:
                self.toggle_history()
            elif self.performance_mode:
                self.toggle_performance()
            elif self.expanded:
                self.toggle_expanded()
            else:
                self.hide()
        elif event.key() == Qt.Key_Return and event.modifiers() & Qt.AltModifier:
            self.toggle_chat()
    
    def showEvent(self, event):
        super().showEvent(event)
        self.reposition()
    
    def quit_app(self):
        self.monitor.stop()
        self.monitor.wait()
        self.tray_icon.hide()
        QApplication.quit()


# ============================================================
# Entry Point
# ============================================================
def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Hermes 灵动岛")

    pet = HermesDesktopPet()
    pet.hide()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
