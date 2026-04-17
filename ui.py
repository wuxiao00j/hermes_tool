# Auto-generated import headers
from config import *
from monitor import ConfigManager, HermesMonitor, send_macos_notification, play_sound
import sys
import os
import re
import time
import json
import sqlite3
from collections import deque
import subprocess
import psutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
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
# macOS integration
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

# Sound support
try:
    from Foundation import NSURL
    from AppKit import NSSound
    SOUND_AVAILABLE = True
except ImportError:
    SOUND_AVAILABLE = False


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
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

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
        # Use explicit rect to avoid offset issues when widget rect isn't at origin
        w, h = self.width(), self.height()
        painter.drawEllipse(QRectF(0, 0, w, h))


# ============================================================
# 多会话指示圆点
# ============================================================
class SessionDots(QWidget):
    """显示次要活跃会话的状态圆点，一个点 = 一个会话"""
    session_clicked = pyqtSignal(int)

    STATUS_COLOR = {
        'working': '#4CAF50',   # 绿
        'thinking': '#FF9800',  # 橙
        'waiting': '#AB47BC',   # 紫
        'error': '#EF5350',     # 红
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sessions: List[Dict] = []
        self.setFixedHeight(14)
        self.setToolTip('')

    def update_sessions(self, sessions: List[Dict], main_session_id=None):
        self._sessions = sessions or []
        self._main_session_id = main_session_id
        dot_width = 14
        # 主会话点更宽(16px)，因为要画外圈
        self.setFixedWidth(max(1, len(self._sessions) * dot_width))
        # tooltip: "会话A (工作中) · 会话B (待命)"
        if self._sessions:
            parts = []
            for s in self._sessions:
                st = s.get('status', 'waiting')
                label = s.get('label', '?')[:20]
                cn = {'working': '工作中', 'thinking': '思考中', 'waiting': '待命', 'error': '异常'}.get(st, st)
                parts.append(f"{label}({cn})")
            self.setToolTip(' · '.join(parts))
        else:
            self.setToolTip('')
        self.update()

    def paintEvent(self, event):
        if not self._sessions:
            return
        from PyQt5.QtGui import QPainter, QColor, QPen
        from PyQt5.QtCore import Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        h = self.height()
        for i, s in enumerate(self._sessions):
            sid = str(s.get('session_id', ''))
            is_main = (sid == str(self._main_session_id)) if self._main_session_id else False
            color = QColor(self.STATUS_COLOR.get(s.get('status', 'waiting'), '#999'))
            x = i * 14 + 1
            if is_main:
                # 主会话点：外圈12px白色边框，内圈8px状态色
                painter.setPen(QPen(Qt.white, 2))
                painter.setBrush(color)
                painter.drawEllipse(x - 2, (h - 12) // 2, 12, 12)
                # 重新画内圈实心
                painter.setPen(Qt.NoPen)
                painter.setBrush(color)
                painter.drawEllipse(x + 2, (h - 8) // 2, 8, 8)
            else:
                # 次要点：6px实心圆
                painter.setPen(Qt.NoPen)
                painter.setBrush(color)
                painter.drawEllipse(x + 4, (h - 6) // 2, 6, 6)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton or not self._sessions:
            return super().mousePressEvent(event)
        index = int(event.x() // 14)
        if 0 <= index < len(self._sessions):
            self.session_clicked.emit(index)
            event.accept()
            return
        super().mousePressEvent(event)


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
# 主题混入类 - 提供主题色工具方法
# ============================================================
class ThemeMixin:
    """混入类，提供主题色工具方法"""
    def _rgba_for_theme(self, dark_rgb: Tuple[int, int, int], light_rgb: Tuple[int, int, int], alpha: int) -> str:
        if self.theme_config == THEMES[Theme.LIGHT]:
            r, g, b = light_rgb
        else:
            r, g, b = dark_rgb
        return f"rgba({r}, {g}, {b}, {alpha})"


# ============================================================
# 历史消息面板 - 修复字体颜色
# ============================================================
class HistoryPanel(ThemeMixin, QFrame):
    message_clicked = pyqtSignal(str)

    def __init__(self, parent=None, theme_config: ThemeConfig = None):
        super().__init__(parent)
        self.theme_config = theme_config or THEMES[Theme.DARK]
        self.setObjectName("historyPanel")
        self.last_messages: List[Dict] = []
        self._item_widgets: Dict[str, QLabel] = {}  # id -> widget for incremental update
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
                background: {self._rgba_for_theme((25, 25, 30), (255, 255, 255), 240)};
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
    
    def _build_message_label(self, msg: Dict, content: str) -> QLabel:
        """为单条消息构建 QLabel widget"""
        role = msg.get("role", "")
        display_text = content[:60] + "..." if len(content) > 60 else content
        
        label = QLabel()
        label.setWordWrap(True)
        label.setCursor(Qt.PointingHandCursor)
        label.message_id = msg.get('id') or f"{role}:{content[:30]}"
        
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
                    background: {self._rgba_for_theme((48, 209, 88), (48, 209, 88), 30)};
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
                    background: {self._rgba_for_theme((255, 255, 255), (0, 0, 0), 20)};
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
                    background: {self._rgba_for_theme((255, 255, 255), (0, 0, 0), 20)};
                    border-radius: 6px;
                }}
            """)
        else:
            return None
        
        label.mousePressEvent = lambda e, c=content: self.message_clicked.emit(c)
        return label

    def update_history(self, messages: List[Dict]):
        """增量更新历史消息"""
        self.last_messages = [dict(msg) if not isinstance(msg, dict) else msg.copy() for msg in messages]
        
        # 收集当前消息的所有有效 id
        current_ids = set()
        for msg in self.last_messages:
            if not isinstance(msg, dict):
                msg = dict(msg)
            role = msg.get("role", "")
            content = msg.get("content", "")
            if isinstance(content, str) and content.startswith('['):
                try:
                    content = json.loads(content)
                except (json.JSONDecodeError, ValueError):
                    pass
            if isinstance(content, list):
                text_parts = [item.get("text", "") for item in content if item.get("type") == "text"]
                content = " ".join(text_parts) if text_parts else "[多模态内容]"
            if not content or content == 'None' or role not in ('user', 'assistant', 'tool'):
                continue
            msg_id = msg.get('id') or f"{role}:{content[:30]}"
            current_ids.add(msg_id)
        
        # 删除已不在列表中的 widget
        removed_ids = set(self._item_widgets.keys()) - current_ids
        for msg_id in removed_ids:
            widget = self._item_widgets.pop(msg_id, None)
            if widget:
                self.messages_layout.removeWidget(widget)
                widget.deleteLater()
        
        # 新增或更新消息
        for msg in self.last_messages:
            if not isinstance(msg, dict):
                msg = dict(msg)
            role = msg.get("role", "")
            content = msg.get("content", "")
            if isinstance(content, str) and content.startswith('['):
                try:
                    content = json.loads(content)
                except (json.JSONDecodeError, ValueError):
                    pass
            if isinstance(content, list):
                text_parts = [item.get("text", "") for item in content if item.get("type") == "text"]
                content = " ".join(text_parts) if text_parts else "[多模态内容]"
            if not content or content == 'None' or role not in ('user', 'assistant', 'tool'):
                continue
            msg_id = msg.get('id') or f"{role}:{content[:30]}"
            
            if msg_id in self._item_widgets:
                continue  # 已存在，跳过
            
            label = self._build_message_label(msg, content)
            if label:
                self._item_widgets[msg_id] = label
                self.messages_layout.addWidget(label)
        
        # 确保 stretch 在最后
        last = self.messages_layout.itemAt(self.messages_layout.count() - 1)
        if self.messages_layout.count() == 0 or (last is not None and not isinstance(last.widget(), QLabel)):
            self.messages_layout.addStretch()


class ActivityPanel(ThemeMixin, QFrame):
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
                background: {self._rgba_for_theme((25, 25, 30), (255, 255, 255), 240)};
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
                    background: {self._rgba_for_theme((255, 255, 255), (0, 0, 0), 12)};
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
                try:
                    names = ", ".join(Path(item).name or item for item in attachments[:2])
                except Exception:
                    names = ", ".join(str(item) for item in attachments[:2])
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
        if isinstance(timestamp_value, (int, float)):
            age = max(0, int(time.time() - float(timestamp_value)))
        else:
            parsed = None
            parent = self.parent()
            if hasattr(parent, "monitor"):
                parsed = parent.monitor._parse_timestamp(timestamp_value)
            else:
                try:
                    text = str(timestamp_value).strip()
                    if text.endswith('Z'):
                        text = text[:-1] + '+00:00'
                    parsed = datetime.fromisoformat(text)
                    if parsed.tzinfo is not None:
                        parsed = parsed.astimezone().replace(tzinfo=None)
                except Exception:
                    parsed = None
            if not parsed:
                return ""
            age = max(0, int((datetime.now() - parsed).total_seconds()))
        if age < 60:
            return f"{age}s 前"
        if age < 3600:
            return f"{age // 60}m 前"
        return f"{age // 3600}h 前"


# ============================================================
# 性能仪表板 - 修复字体颜色
# ============================================================
class PerformancePanel(ThemeMixin, QFrame):
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
                background: {self._rgba_for_theme((25, 25, 30), (255, 255, 255), 240)};
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
# 未翻译词设置对话框
# ============================================================
class TranslationSettingsDialog(QDialog):
    translations_changed = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("翻译设置")
        self.resize(500, 420)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("""
            QDialog {
                background: rgba(30, 30, 35, 250);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 12px;
            }
            QLabel {
                color: rgba(255, 255, 255, 220);
            }
            QGroupBox {
                color: rgba(255, 255, 255, 200);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QLineEdit {
                background: rgba(255, 255, 255, 10);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 6px;
                padding: 6px 10px;
                color: rgba(255, 255, 255, 220);
                selection-background-color: rgba(48, 209, 88, 110);
            }
            QLineEdit:focus {
                border: 1px solid rgba(48, 209, 88, 150);
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
            QPushButton[secondary="true"] {
                background: rgba(255, 255, 255, 30);
            }
            QPushButton[secondary="true"]:hover {
                background: rgba(255, 255, 255, 50);
            }
            QScrollArea {
                background: transparent;
                border: none;
            }
            QWidget#scrollContent {
                background: transparent;
            }
        """)
        self._data = {}
        self._load()
        self._build_ui()

    def _load(self):
        self._data = {}
        if Path(UNKNOWN_TRANSLATIONS_FILE).exists():
            try:
                self._data = json.loads(Path(UNKNOWN_TRANSLATIONS_FILE).read_text())
            except Exception:
                pass

    def _save(self):
        try:
            Path(UNKNOWN_TRANSLATIONS_FILE).parent.mkdir(parents=True, exist_ok=True)
            Path(UNKNOWN_TRANSLATIONS_FILE).write_text(json.dumps(self._data, ensure_ascii=False, indent=2))
        except Exception:
            pass

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 说明
        info = QLabel("以下为检测到的未翻译原文。填写翻译后点击保存，下次将自动使用。")
        info.setWordWrap(True)
        info.setStyleSheet("color: rgba(255,255,255,140); font-size: 12px;")
        layout.addWidget(info)

        # 列表
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("border: none;")
        scroll_content = QWidget()
        scroll_content.setObjectName("scrollContent")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(8)

        self._row_widgets = []  # [(key, raw_label, translation_input)]

        untranslated = {k: v for k, v in self._data.items() if not v.get("translation", "").strip()}
        translated = {k: v for k, v in self._data.items() if v.get("translation", "").strip()}

        if not self._data:
            empty_label = QLabel("暂无未翻译记录")
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet("color: rgba(255,255,255,100); padding: 20px;")
            scroll_layout.addWidget(empty_label)
        else:
            # 未翻译优先显示
            for key in sorted(untranslated.keys()):
                self._add_row(scroll_layout, key, untranslated[key])
            if untranslated and translated:
                separator = QLabel("── 已填写翻译 ──")
                separator.setAlignment(Qt.AlignCenter)
                separator.setStyleSheet("color: rgba(255,255,255,60); font-size: 11px; padding: 4px;")
                scroll_layout.addWidget(separator)
            for key in sorted(translated.keys()):
                self._add_row(scroll_layout, key, translated[key])

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        clear_btn = QPushButton("清空已翻译")
        clear_btn.setProperty("secondary", True)
        clear_btn.clicked.connect(self._clear_translated)
        btn_row.addWidget(clear_btn)

        btn_row.addStretch()

        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self._do_save)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

    def _add_row(self, parent_layout, key: str, entry: dict):
        raw = entry.get("raw", "")
        translation = entry.get("translation", "")

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        raw_label = QLabel(raw[:60] + ("..." if len(raw) > 60 else ""))
        raw_label.setStyleSheet("color: rgba(255,255,255,160); font-size: 12px;")
        raw_label.setWordWrap(False)
        raw_label.setFixedWidth(180)
        raw_label.setToolTip(raw)

        translation_input = QLineEdit()
        translation_input.setPlaceholderText("输入翻译...")
        translation_input.setText(translation)
        translation_input.setMinimumWidth(200)
        row_layout.addWidget(raw_label)
        row_layout.addWidget(translation_input, 1)

        parent_layout.addWidget(row)
        self._row_widgets.append((key, raw_label, translation_input))

    def _clear_translated(self):
        keys_to_remove = [k for k, v in self._data.items() if v.get("translation", "").strip()]
        for k in keys_to_remove:
            del self._data[k]
        self._save()
        # Rebuild UI
        while self.layout().count() > 1:
            item = self.layout().takeAt(1)
            if item.widget():
                item.widget().deleteLater()
        self._build_ui()

    def _do_save(self):
        for key, raw_label, translation_input in self._row_widgets:
            if key in self._data:
                self._data[key]["translation"] = translation_input.text().strip()
        self._save()
        self.translations_changed.emit(self._get_translation_dict())
        self.accept()

    def _get_translation_dict(self) -> dict:
        return {v["raw"]: v["translation"] for v in self._data.values() if v.get("translation", "").strip()}


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
        self.resize(420, 700)
        self.setMinimumSize(400, 600)
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

        self.settings_scroll = QScrollArea()
        self.settings_scroll.setObjectName("settingsScroll")
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setFrameShape(QFrame.NoFrame)
        self.settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.settings_scroll.viewport().setObjectName("settingsViewport")
        outer_layout.addWidget(self.settings_scroll)

        self.settings_content = QWidget()
        self.settings_content.setObjectName("settingsContent")
        self.settings_scroll.setWidget(self.settings_content)

        layout = QVBoxLayout(self.settings_content)
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

        translate_btn = QPushButton("翻译设置")
        translate_btn.setProperty("secondary", True)
        translate_btn.clicked.connect(self._open_translation_settings)
        layout.addWidget(translate_btn)

        apply_btn = QPushButton("应用")
        apply_btn.clicked.connect(self.apply_theme)
        layout.addWidget(apply_btn)
        self._apply_combo_popup_theme()
        QTimer.singleShot(0, self._refresh_dialog_layout)

    def _open_translation_settings(self):
        dialog = TranslationSettingsDialog(self)
        dialog.translations_changed.connect(self._on_translations_changed)
        dialog.exec_()

    def _on_translations_changed(self, translation_dict: dict):
        # Persist to window runtime
        self.parent()._custom_translations = translation_dict
        # Notify monitor
        if hasattr(self.parent(), 'monitor'):
            self.parent().monitor.set_custom_translations(translation_dict)

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

    def _refresh_dialog_layout(self):
        self.layout().activate()
        if hasattr(self, 'settings_content'):
            self.settings_content.adjustSize()
        if hasattr(self, 'settings_scroll'):
            self.settings_scroll.widget().adjustSize()
            self.settings_scroll.viewport().updateGeometry()
        self.adjustSize()
        self.updateGeometry()

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
        self._refresh_dialog_layout()

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
        self._refresh_dialog_layout()

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
        self._refresh_dialog_layout()

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
        self._refresh_dialog_layout()

    def on_session_changed(self, index: int):
        data = self.session_combo.itemData(index)
        if not data:
            return
        session_mode, session_id = data
        self.session_mode = session_mode
        self.selected_session_id = session_id
        self.session_changed.emit(session_mode, session_id)
        self._refresh_dialog_layout()

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
            self._refresh_dialog_layout()

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
    CLICK_DRAG_THRESHOLD = 6

    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.expanded = False
        self.detail_text = "Hermes 就绪"
        self.full_detail_text = self.detail_text
        self.status_name = "待机中"
        self.metadata = {}
        self.current_theme = Theme.DARK
        self.status_colors = DEFAULT_STATUS_COLORS.copy()
        self.theme_config = THEMES[self.current_theme]
        self._press_pos = None
        self._animation_queue = deque(maxlen=5)  # 动画队列，最多 5 个
        self._animating = False
        self._collapsed = False  # 智能缩进状态

        self.setObjectName("dynamicIsland")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)
        
        # 鼠标跟踪
        self.setMouseTracking(True)
        
        self.apply_theme()
        self.setup_ui()

    @property
    def collapsed(self):
        return self._collapsed
    
    @collapsed.setter
    def collapsed(self, val):
        self._collapsed = val

    def resize_if_needed(self):
        """由 set_collapsed / set_collapsed_visual 调用，触发父窗口 resize"""
        if self.parent():
            size = self.calculate_size(self.expanded)
            self.parent().resize_for_content(size)

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
        
        # 动态 border-radius: 保证即使展开也不会变方形；collapsed 时直接做成圆球
        height = self.height()
        if self.collapsed:
            radius = max(10, height // 2)
        else:
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
            compact_height = 64 if ('\n' in (self.full_detail_text or '')) else 52
            return QSize(base_width, compact_height)
        
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
        self.setFixedWidth(self.EXPANDED_WIDTH if expanded else self.COMPACT_WIDTH)

        if self.expanded and self.metadata:
            meta_text = self._format_metadata()
            self.meta_label.setText(meta_text)
            self.meta_label.show()
            self.meta_label.adjustSize()
        else:
            self.meta_label.hide()

        self._update_detail_label()
        self.updateGeometry()
        self.adjustSize()

        if self.parent():
            size = self.calculate_size(expanded)
            self.parent().resize_for_content(size)
        self.apply_theme()

    def set_collapsed(self, val: bool = True, trigger_resize: bool = True, immediate: bool = False):
        """Set collapsed state.
        
        Args:
            val: True to collapse, False to expand
            trigger_resize: Whether to trigger window resize (set_collapsed_visual bypasses this)
            immediate: Skip animation queue, set directly
        """
        if immediate:
            self._collapsed = val
            self._update_visual_state()
            if trigger_resize:
                self.resize_if_needed()
            return
        
        if self._collapsed == val:
            return
        
        if self._animating:
            # 入队，等当前动画完成
            self._animation_queue.append((val, trigger_resize))
            return
        
        self._animating = True
        self._collapsed = val
        self._animate_collapse(self._collapsed, lambda: self._on_collapse_done(trigger_resize))

    def set_collapsed_visual(self, val: bool):
        """仅更新视觉状态，不触发窗口 resize（向后兼容）"""
        self.set_collapsed(val, trigger_resize=False)

    def _update_visual_state(self):
        """更新视觉效果（展开/收起）"""
        if self.collapsed:
            self.main_layout.setContentsMargins(0, 0, 0, 0)
            self.main_layout.setSpacing(0)
            self.top_row.setContentsMargins(0, 0, 0, 0)
            self.top_row.setSpacing(0)
            self.top_row.setAlignment(Qt.AlignCenter)
            self.setFixedSize(self.COLLAPSED_WIDTH, self.COLLAPSED_HEIGHT)
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
            self.top_row.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.setMinimumSize(0, 0)
            self.setMaximumSize(16777215, 16777215)
            self.setFixedWidth(self.EXPANDED_WIDTH if self.expanded else self.COMPACT_WIDTH)
            self.detail_label.show()
            self.chevron_label.show()
            self.status_dot.show()
            self.status_dot.setFixedSize(12, 12)
            if self.expanded:
                self.meta_label.show()
            else:
                self.meta_label.hide()
        self.apply_theme()
        self._update_detail_label()

    def _animate_collapse(self, collapsing: bool, callback=None):
        """执行动画，如果已有动画在执行则加入队列"""
        def execute():
            self._update_visual_state()
            if callback:
                callback()
            self._animating = False
            # 出队执行下一个
            if self._animation_queue:
                next_anim = self._animation_queue.popleft()
                val, trigger_resize = next_anim
                self._animating = True
                self._collapsed = val
                self._animate_collapse(val, lambda: self._on_collapse_done(trigger_resize))
        
        # 立即执行视觉效果更新（无真正动画，因为外层窗口控制动画）
        execute()

    def _on_collapse_done(self, trigger_resize: bool):
        if trigger_resize:
            self.resize_if_needed()

    def _set_content_opacity(self, opacity: float):
        return

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

        # （其他活跃会话已禁用）

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

    def _build_idle_secondary_line(self) -> str:
        parts = []
        if self.metadata.get('cron_next_run_at'):
            parts.append(f"下次 {self._format_clock_value(self.metadata.get('cron_next_run_at'))}")
        recent_activity = self.metadata.get('recent_activity') or []
        if recent_activity:
            parts.append(self._clip_text(recent_activity[-1], 18))
        elif self.metadata.get('cron_last_status'):
            parts.append(f"任务 {self.metadata.get('cron_last_status')}")
        stage = self._derive_collaboration_stage()
        if stage and len(parts) < 2:
            parts.append(stage)
        return " · ".join(parts[:2])

    def _build_standard_compact_line(self, raw_detail: str) -> str:
        raw_detail = (raw_detail or '').strip()
        cron_name = str(self.metadata.get('cron_name') or '').strip()
        next_run = self._format_clock_value(self.metadata.get('cron_next_run_at')) if self.metadata.get('cron_next_run_at') else ''
        is_paused = self.metadata.get('cron_state') == 'paused'
        has_meaningful_detail = bool(raw_detail and raw_detail not in {'等待指令', '等待输入', '空闲中'} and raw_detail not in LOW_INFORMATION_STATUS_TEXTS)
        if self.current_status == 'waiting' and self.metadata.get('cron_configured'):
            if is_paused:
                return "自动推进已暂停"
            if cron_name and next_run and next_run != '—':
                return f"{cron_name} · 下次 {next_run}"
            if cron_name:
                return cron_name
            if next_run and next_run != '—':
                return f"下次 {next_run}"
        if has_meaningful_detail:
            return raw_detail
        if is_paused:
            return "自动推进已暂停"
        if cron_name and next_run and next_run != '—':
            return f"{cron_name} · 下次 {next_run}"
        if cron_name:
            return cron_name
        if next_run and next_run != '—':
            return f"下次 {next_run}"
        return raw_detail

    def _update_detail_label(self):
        compact_mode = not self.expanded or self.collapsed
        raw_full = self.full_detail_text or ""
        detail = raw_full.replace("\n", " ")
        if self.collapsed:
            self.detail_label.setWordWrap(False)
            self.detail_label.setFixedHeight(24)
            available_width = max(80, self.COMPACT_WIDTH - self.PADDING - 30)
            elided = QFontMetrics(self.detail_label.font()).elidedText(detail, Qt.ElideRight, available_width)
            self.detail_label.setText(elided)
        elif compact_mode:
            self.detail_label.setWordWrap(False)
            self.detail_label.setFixedHeight(24)
            available_width = max(80, self.COMPACT_WIDTH - self.PADDING - 30)
            elided = QFontMetrics(self.detail_label.font()).elidedText(detail, Qt.ElideRight, available_width)
            self.detail_label.setText(elided)
        else:
            # 展开状态：先写入文本，再按内容重新计算高度
            self.detail_label.setWordWrap(True)
            self.detail_label.setText(raw_full)
            self.detail_label.setFixedHeight(16777215)
            self.detail_label.adjustSize()
            self.detail_label.setFixedHeight(max(24, self.detail_label.sizeHint().height()))

    def set_status(self, status: str, detail: str, metadata: dict = None):
        self.current_status = status
        self.metadata = metadata or {}
        raw_detail = detail or ""
        display_detail = raw_detail
        if status in ('waiting', 'idle', 'success') and not self.expanded and not self.collapsed:
            display_detail = self._build_standard_compact_line(raw_detail)
        self.full_detail_text = display_detail
        self.detail_text = self.full_detail_text

        color = self.status_colors.get(status, "#8E8E93")
        pulsing = status in ("thinking", "working")

        self.status_dot.set_color(color)
        self.status_dot.set_pulsing(pulsing)
        self._update_detail_label()

        if self.expanded:
            meta_text = self._format_metadata()
            self.meta_label.setText(meta_text)
            self._update_detail_label()
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
            self._press_pos = event.pos()
            event.accept()
        elif event.button() == Qt.RightButton:
            event.ignore()
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._press_pos is not None:
            moved = (event.pos() - self._press_pos).manhattanLength()
            self._press_pos = None
            if moved <= self.CLICK_DRAG_THRESHOLD:
                self.clicked.emit()
            event.accept()
        else:
            super().mouseReleaseEvent(event)


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
        self._last_cron_failure_signature = None
        self._last_completed_actions = []  # 最近完成的动作队列，最多 3 条
        self._working_since = None
        self._progress_signature = None
        self._progress_changed_at = None
        self._last_status_payload = None
        self._last_debug_log_signature = None
        self._last_activity_refresh_signature = None
        
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

        # （多会话轮询已禁用）

        # 自定义翻译（用户通过翻译设置页填写的）
        self._custom_translations = {}

        # 最近动作面板开关
        self.activity_panel_visible = self.config.config.get("activity_panel_visible", True)
        
        # 展开动画
        self.expand_animation = None
        self.collapse_animation = None
        self._animating = False  # 动画期间禁止 resize_for_content
        self._expanded_before_collapse = False
        self._drag_start_pos = None
        self._mouse_inside = False
        self._menu_open = False
        
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
        self.apply_requested_auto_hide_timeout(self.config.config.get("auto_hide_timeout", 10))

        self.reset_auto_hide_timer()
    
    def _menu_stylesheet(self) -> str:
        theme = self.current_theme_config
        menu_bg = theme.bg_color if theme == THEMES[Theme.LIGHT] else "rgba(30, 30, 35, 245)"
        item_hover = theme.accent_color
        text_color = theme.text_color
        return f"""
            QMenu {{
                background: {menu_bg};
                border: 1px solid {theme.border_color};
                border-radius: 8px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 8px 24px;
                border-radius: 4px;
                color: {text_color};
            }}
            QMenu::item:selected {{
                background: {item_hover};
            }}
            QMenu::separator {{
                height: 1px;
                background: {theme.border_color};
                margin: 4px 8px;
            }}
        """

    def _target_rect_for_size(self, size: QSize) -> QRect:
        current = self.geometry()
        width = max(1, size.width())
        height = max(1, size.height())
        if self.is_snapped:
            return QRect(current.x(), current.y(), width, height)
        screen = QApplication.primaryScreen().geometry()
        x = screen.x() + (screen.width() - width) // 2
        y = screen.y() + 6
        return QRect(x, y, width, height)

    def _animate_window_resize(self, target_rect: QRect, duration: int = 220):
        if hasattr(self, '_window_resize_anim') and self._window_resize_anim:
            self._window_resize_anim.stop()
        self._animating = True
        self._window_resize_anim = QPropertyAnimation(self, b"geometry", self)
        self._window_resize_anim.setDuration(duration)
        self._window_resize_anim.setStartValue(self.geometry())
        self._window_resize_anim.setEndValue(target_rect)
        self._window_resize_anim.setEasingCurve(QEasingCurve.InOutCubic)
        self._window_resize_anim.finished.connect(self._finish_window_resize)
        self._window_resize_anim.start()

    def _finish_window_resize(self):
        self._animating = False

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

    def resize_for_content(self, island_size: QSize, animate: bool = False):
        if self._animating and not animate:
            return
        if self.is_collapsed:
            orb_outer = max(48, DynamicIslandWidget.COLLAPSED_WIDTH + 20)
            self.setFixedSize(orb_outer, orb_outer)
            self.reposition()
            return
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
        target_size = QSize(total_width, total_height)
        if animate:
            self._animate_window_resize(self._target_rect_for_size(target_size))
        else:
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
        self.resize_for_content(current_size, animate=True)
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
        self._mouse_inside = True
        try:
            if self.is_collapsed:
                self.expand_from_collapsed()
            self.reset_auto_hide_timer()
        except Exception as e:
            print(f"on_mouse_enter failed: {e}", file=sys.stderr)

    def on_mouse_leave(self):
        """鼠标离开岛屿区域"""
        self._mouse_inside = False
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
        if self._menu_open or self._mouse_inside or self.underMouse() or self.content_scroll.underMouse():
            return
        cursor_pos = self.mapFromGlobal(QCursor.pos())
        if self.rect().contains(cursor_pos):
            return
        self.collapse_to_edge()
    
    def _build_collapsed_geometry(self) -> QRect:
        """收拢后的圆球外框：固定正方形，居中于原始灵动岛"""
        ref = self.last_uncollapsed_geometry if self.last_uncollapsed_geometry.width() > 0 else self.geometry()
        orb_outer = max(48, self.island.COLLAPSED_WIDTH + 20)
        target_x = ref.x() + (ref.width() - orb_outer) // 2
        target_y = ref.y() + (ref.height() - orb_outer) // 2
        return QRect(target_x, target_y, orb_outer, orb_outer)

    def _animate_content_opacity(self, start: float, end: float, duration: int = 220, delay: int = 0):
        group = QParallelAnimationGroup(self)
        if delay > 0:
            group.addAnimation(QPauseAnimation(delay))
        return group

    def collapse_to_edge(self):
        """收拢：先切到圆球视觉，再同步缩放与淡出内容。"""
        if self.is_collapsed or self._animating:
            return
        self.last_uncollapsed_geometry = self.geometry()
        self._expanded_before_collapse = self.expanded
        self.is_collapsed = True
        self.update_auxiliary_visibility()
        self._animating = True

        start = self.geometry()
        target = self._build_collapsed_geometry()
        self.island.set_collapsed_visual(True)
        self.island._set_content_opacity(1.0)

        geo_anim = QPropertyAnimation(self, b"geometry", self)
        geo_anim.setDuration(340)
        geo_anim.setStartValue(start)
        geo_anim.setEndValue(target)
        geo_anim.setEasingCurve(QEasingCurve.InOutCubic)

        self._collapse_group = QParallelAnimationGroup(self)
        self._collapse_group.addAnimation(geo_anim)
        self._collapse_group.addAnimation(self._animate_content_opacity(1.0, 0.0, 180, delay=0))
        self._collapse_group.finished.connect(self._on_collapse_finished)
        self._collapse_group.start()

    def _on_collapse_finished(self):
        self._animating = False
        self.setMinimumSize(1, 1)
        self.setMaximumSize(self.WINDOW_WIDTH, 800)
        self.island.set_collapsed(True)
        self.island._set_content_opacity(0.0)

    def expand_from_collapsed(self, emphasize: bool = False):
        """展开：保持圆球几何先扩展，再平滑恢复内容与长条视觉。"""
        if not self.is_collapsed or self._animating:
            return
        ref = self.last_uncollapsed_geometry if self.last_uncollapsed_geometry.width() > 0 else QRect(self.x(), self.y(), self.WINDOW_WIDTH, 52)
        restore_expanded = self._expanded_before_collapse
        self.is_collapsed = False
        self.expanded = restore_expanded
        self._animating = True

        self.island.set_collapsed_visual(True)
        self.island._set_content_opacity(0.0)
        self.update_auxiliary_visibility()

        start = self.geometry()
        geo_anim = QPropertyAnimation(self, b"geometry", self)
        geo_anim.setDuration(360)
        geo_anim.setStartValue(start)
        geo_anim.setEndValue(ref)
        geo_anim.setEasingCurve(QEasingCurve.InOutCubic)

        self._expand_group = QParallelAnimationGroup(self)
        self._expand_group.addAnimation(geo_anim)
        self._expand_group.finished.connect(lambda: self._on_expand_finished(ref))
        self._expand_group.start()
        if emphasize:
            self.animate_status_change()

    def _on_expand_finished(self, target: QRect):
        self._animating = False
        self.setMinimumWidth(self.island.COLLAPSED_WIDTH + 20)
        self.setMaximumWidth(self.WINDOW_WIDTH)
        self.island.set_collapsed(False)
        self.island.set_expanded(self.expanded)
        self.update_auxiliary_visibility()
        self.island._set_content_opacity(0.0)

        current_size = self.island.calculate_size(self.expanded)
        self.resize_for_content(current_size)

        self._expand_content_group = self._animate_content_opacity(0.0, 1.0, 220, delay=0)
        self._expand_content_group.start()
    
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

    def _flash_island(self, duration_ms: int = 400):
        """短暂闪动灵动岛，提示切换发生"""
        if not hasattr(self, 'island'):
            return
        effect = self.island.graphicsEffect()
        if effect is None:
            effect = QGraphicsOpacityEffect(self.island)
            self.island.setGraphicsEffect(effect)

        anim = QPropertyAnimation(effect, b"opacity")
        anim.setDuration(duration_ms)
        anim.setStartValue(1.0)
        anim.setKeyValueAt(0.5, 0.3)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.InOutCubic)
        anim.start(QAbstractAnimation.DeleteWhenStopped)

    def _status_payload_signature(self, status: str, detail: str, metadata: dict) -> tuple:
        metadata = metadata or {}
        return (
            status,
            detail,
            metadata.get('status_reason'),
            metadata.get('cron_name'),
            metadata.get('cron_next_run_at'),
            tuple((metadata.get('recent_activity') or [])[-2:]),
            tuple((metadata.get('recent_live_activity') or [])[-2:]),
            tuple((metadata.get('recent_files') or [])[:2]),
            metadata.get('live_detail'),
            metadata.get('resolved_session_id'),
        )

    def _debug_log_signature(self, status: str, detail: str, metadata: dict) -> tuple:
        metadata = metadata or {}
        return (
            status,
            detail,
            metadata.get('status_reason'),
            metadata.get('live_detail'),
            tuple((metadata.get('recent_activity') or [])[-2:]),
            metadata.get('cron_last_status'),
            metadata.get('cron_next_run_at'),
        )

    def _progress_signature_for_status(self, detail: str, metadata: dict) -> str:
        metadata = metadata or {}
        recent_activity = metadata.get('recent_activity') or []
        latest_activity = str(recent_activity[-1]) if recent_activity else ''
        live_detail = str(metadata.get('live_detail') or '')
        last_msg = str(metadata.get('last_message_timestamp') or '')
        return " | ".join([detail or '', live_detail, latest_activity, last_msg])[:240]

    def _derive_live_headline(self, status: str, detail: str, metadata: Dict[str, Any]) -> str:
        metadata = metadata or {}
        live_detail = str(metadata.get('live_detail') or '').strip()
        if metadata.get('status_reason') == 'runtime_live_activity' and live_detail and live_detail not in LOW_INFORMATION_STATUS_TEXTS:
            return live_detail
        if status not in ('working', 'thinking'):
            return detail

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
                # 去重：不连续追加相同的动作
                if not self._last_completed_actions or self._last_completed_actions[-1] != meaningful:
                    self._last_completed_actions.append(meaningful)
                    self._last_completed_actions = self._last_completed_actions[-3:]  # 最多保留 3 条
        elif status in ('working', 'thinking'):
            self._last_completed_actions = []

        # （主会话结束 → 自动切换已禁用）

        recent_activity = metadata.get("recent_activity") or []
        low_information_detail = detail in LOW_INFORMATION_STATUS_TEXTS
        if (detail in ("正在处理...", "处理中...", "处理中", "等待指令") or low_information_detail) and recent_activity:
            latest_activity = self.monitor._activity_core(recent_activity[-1]) if hasattr(self, 'monitor') else str(recent_activity[-1])
            if latest_activity and latest_activity not in LOW_INFORMATION_STATUS_TEXTS:
                detail = latest_activity[:64]
        elif detail in ("正在处理...", "处理中...", "处理中", "等待指令") or low_information_detail:
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
        payload_signature = self._status_payload_signature(status, detail, metadata)

        # （"刚完成"摘要已移除，保持单行显示）

        # 卡住检测（降低误报：必须持续 working、且进展签名长时间不变）
        if status == 'working':
            now_ts = time.time()
            progress_signature = self._progress_signature_for_status(detail, metadata)
            if old_status != 'working' or self._working_since is None:
                self._working_since = now_ts
                self._progress_signature = progress_signature
                self._progress_changed_at = now_ts
            else:
                if progress_signature != self._progress_signature:
                    self._progress_signature = progress_signature
                    self._progress_changed_at = now_ts
                elapsed = now_ts - self._working_since
                stagnant_for = now_ts - (self._progress_changed_at or now_ts)
                live_age = metadata.get('live_age_seconds')
                if elapsed > 90 and stagnant_for > 45 and (live_age is None or live_age > 25):
                    detail = f"⚠️ 疑似卡住 · {int(stagnant_for)}s 无明显进展"
        else:
            self._working_since = None
            self._progress_signature = None
            self._progress_changed_at = None

        debug_signature = self._debug_log_signature(status, detail, metadata)
        if debug_signature != self._last_debug_log_signature and hasattr(self, 'monitor'):
            self._last_debug_log_signature = debug_signature
            self.monitor._append_pet_debug_log(status, detail, metadata)

        self.current_detail = detail

        if status == 'waiting' and old_status == 'working' and not self.expanded and not self.is_collapsed:
            self.island.set_status(status, detail, metadata)
            QApplication.processEvents()

        if payload_signature != self._last_status_payload:
            self._last_status_payload = payload_signature
            self.island.set_status(status, detail, metadata)
        if hasattr(self, 'tray_icon'):
            self.tray_icon.setIcon(self._build_tray_icon(status))
            self.tray_icon.setToolTip(self._build_tray_tooltip(status, detail, metadata))
        activity_refresh_signature = tuple((metadata.get("recent_activity") or [])[-4:])
        if self.expanded and isinstance(metadata, dict) and metadata.get("recent_activity") and activity_refresh_signature != self._last_activity_refresh_signature:
            self._last_activity_refresh_signature = activity_refresh_signature
            if not self.activity_panel.events:
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

        # cron 失败通知
        cron_status = metadata.get('cron_last_status')
        if cron_status and cron_status not in ('ok', 'waiting', 'pending', ''):
            cron_err = metadata.get('cron_last_error') or metadata.get('cron_last_delivery_error') or detail or '未知错误'
            failure_signature = (metadata.get('cron_last_run_at'), cron_status, str(cron_err)[:80])
            if failure_signature != self._last_cron_failure_signature:
                self._last_cron_failure_signature = failure_signature
                notify_lines = []
                if metadata.get('cron_name'):
                    notify_lines.append(str(metadata['cron_name']))
                notify_lines.append(f"状态: {cron_status}")
                notify_lines.append(str(cron_err)[:120])
                send_macos_notification('Hermes 任务异常', ' · '.join(notify_lines), sound=True)

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
        self._status_anim.setDuration(320)
        self._status_anim.setStartValue(0.72)
        self._status_anim.setEndValue(1.0)
        self._status_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._status_anim.start()
    
    # ============================================================
    # 右键菜单和快捷操作
    # ============================================================
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet(self._menu_stylesheet())
        self._menu_open = True

        chat_action = QAction("💬 发送消息", self)
        chat_action.triggered.connect(self.toggle_chat)
        menu.addAction(chat_action)

        menu.addSeparator()

        quick_menu = menu.addMenu("⚡ 快捷消息")
        quick_menu.setStyleSheet(self._menu_stylesheet())
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
        cron_menu.setStyleSheet(self._menu_stylesheet())
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
            instance_menu.setStyleSheet(self._menu_stylesheet())
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

        try:
            menu.exec_(event.globalPos())
        finally:
            self._menu_open = False
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

        self.current_theme_config = THEMES[Theme(theme)]
        self.island.set_theme(theme, status_colors)
        self.chat_input.update_theme(self.current_theme_config)
        self.history_panel.update_theme(self.current_theme_config)
        self.activity_panel.update_theme(self.current_theme_config)
        self.performance_panel.update_theme(self.current_theme_config)

        self.STATUS_COLORS = status_colors
        self.setWindowOpacity(opacity / 100.0)
        self.init_tray()
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

        # 显示 loading 态
        self.island.set_status('thinking', '切换中...')
        self.island.setToolTip('正在切换会话...')

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
        self._flash_island()
        self.island.setToolTip('')

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
        tray_menu.setStyleSheet(self._menu_stylesheet())

        show_action = QAction("显示", self)
        show_action.triggered.connect(self.show)
        tray_menu.addAction(show_action)

        chat_action = QAction("发送消息", self)
        chat_action.triggered.connect(self.toggle_chat)
        tray_menu.addAction(chat_action)

        cron_menu = tray_menu.addMenu("⏱ 定时任务")
        cron_menu.setStyleSheet(self._menu_stylesheet())
        self._populate_cron_menu(cron_menu)

        tray_menu.addSeparator()

        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.quit_app)
        tray_menu.addAction(quit_action)

        if hasattr(self, 'tray_icon'):
            self.tray_icon.setContextMenu(tray_menu)
            self.tray_icon.setIcon(self._build_tray_icon(self.current_status))
            return

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
            self._drag_start_pos = event.globalPos()
            self.drag_position = event.globalPos() - self.pos()
            self.is_dragging = False
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() & Qt.LeftButton and self.drag_position is not None:
            if not self.is_dragging and self._drag_start_pos is not None:
                moved = (event.globalPos() - self._drag_start_pos).manhattanLength()
                if moved >= DynamicIslandWidget.CLICK_DRAG_THRESHOLD:
                    self.is_dragging = True
            if self.is_dragging:
                new_pos = event.globalPos() - self.drag_position
                self.move(new_pos)
                self.is_snapped = False
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and self.drag_position is not None:
            if self.is_dragging:
                self.is_dragging = False
                self.check_snap_to_edge()
                self.reset_auto_hide_timer()
                event.accept()
            self.drag_position = None
            self._drag_start_pos = None
            return
        super().mouseReleaseEvent(event)
    
    def check_snap_to_edge(self):
        pos = self.pos()
        size = self.size()
        threshold = self.snap_threshold
        best = None  # (distance, target_pos)

        for screen in QApplication.screens():
            g = screen.geometry()
            # 窗口在该屏幕范围内的重叠面积
            overlap_left = max(pos.x(), g.x())
            overlap_top = max(pos.y(), g.y())
            overlap_right = min(pos.x() + size.width(), g.x() + g.width())
            overlap_bottom = min(pos.y() + size.height(), g.y() + g.height())
            if overlap_left >= overlap_right or overlap_top >= overlap_bottom:
                continue  # 完全不在这个屏幕内

            # 左边缘
            dist = pos.x() - g.x()
            if 0 <= dist < threshold:
                candidate = (dist, QPoint(g.x() + 10, pos.y()))
                if best is None or candidate[0] < best[0]:
                    best = candidate
            # 右边缘
            dist = (g.x() + g.width()) - (pos.x() + size.width())
            if 0 <= dist < threshold:
                candidate = (dist, QPoint(g.x() + g.width() - size.width() - 10, pos.y()))
                if best is None or candidate[0] < best[0]:
                    best = candidate
            # 上边缘
            dist = pos.y() - g.y()
            if 0 <= dist < threshold:
                candidate = (dist, QPoint(pos.x(), g.y() + 6))
                if best is None or candidate[0] < best[0]:
                    best = candidate
            # 下边缘
            dist = (g.y() + g.height()) - (pos.y() + size.height())
            if 0 <= dist < threshold:
                candidate = (dist, QPoint(pos.x(), g.y() + g.height() - size.height() - 10))
                if best is None or candidate[0] < best[0]:
                    best = candidate

        if best is not None:
            self.animate_snap(best[1])
            self.is_snapped = True
    
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
