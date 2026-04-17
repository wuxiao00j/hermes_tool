# Auto-generated import from config (all constants + stdlib deps)
from config import *
import sqlite3
import json
import subprocess
import psutil
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QApplication
from collections import OrderedDict

# Live activity thresholds
LIVE_ACTIVITY_MAX_AGE_SEC = 20
LIVE_ACTIVITY_STALE_SEC = 90
LIVE_ACTIVITY_STAGNANT_SEC = 45
LIVE_ACTIVITY_RED_AGE = 300
LIVE_ACTIVITY_YELLOW_AGE = 180
LIVE_ACTIVITY_FRESH_WORKING_SEC = 8  # threshold for considering live activity actively working
TERMINAL_ACTIVITY_HOLD_SEC = 60
# Health check thresholds
HEALTH_CHECK_INTERVAL = 5
HEALTH_STALE_SEC = 45
# Animation durations
ANIMATION_FAST_MS = 150
ANIMATION_NORMAL_MS = 300
ANIMATION_SLOW_MS = 500
# Token limits
TOKEN_WARN_THRESHOLD=7000
TOKEN_CRITICAL_THRESHOLD=8000
# Debug log rotation
MAX_DEBUG_LOG_SIZE = 1000
MAX_DEBUG_LOG_BYTES = 5 * 1024 * 1024

# Tool target key mapping for generic extraction
TOOL_TARGET_KEYS = {
    "read": "path",
    "write": "path",
    "edit": "path",
    "read_file": "path",
    "write_file": "path",
    "patch": "path",
    "grep": "pattern",
    "navigate": "url",
    "browser_navigate": "url",
    "browser_use": "url",
    "browser_cdp": "url",
    "browser_c": "url",
    "snapshot": "target",
    "shell": "command",
    "search": "query",
}
TOOL_PATH_KEYS = {"read", "write", "edit", "read_file", "write_file", "patch"}
TOOL_URL_KEYS = {"navigate", "browser_navigate", "browser_use", "browser_cdp", "browser_c"}
TOOL_PATTERN_KEYS = {"grep"}
TOOL_TRUNCATE = {
    "snapshot": 24,
    "shell": 38,
    "search": 36,
}

# macOS 通知支持 (UserNotifications - modern API,取代废弃的 NSUserNotification)
try:
    import UserNotifications
    UN_AVAILABLE = False
except ImportError:
    UN_AVAILABLE = True

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
        self._instance_id = instance_id or self.GLOBAL_AGENT_OPTION
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
        self._gateway_status_cache = {
            "checked_at": 0.0,
            "running": False,
            "info": {},
        }
        self._live_session_cache: OrderedDict[str, Tuple[float, Dict[str, Any]]] = OrderedDict()
        self._MAX_CACHE_ENTRIES = 100
        self._db_conn = None
        self._signal_connections = []  # 存储 (signal, slot) 元组，用于断开连接
        self._custom_translations: Dict[str, str] = {}  # 用户自定义翻译
        self._terminal_activity_hold_until = 0.0
        self._terminal_activity_detail = ""

    def set_custom_translations(self, translations: Dict[str, str]):
        """设置用户自定义翻译字典"""
        self._custom_translations = translations

    def _reload_translation_labels(self, translation_dict: Dict[str, str]):
        """重新加载自定义翻译到运行时（通过替换模块级变量引用）"""
        self._custom_translations = translation_dict

    def _match_substring_label(self, content: str, labels: list) -> Optional[str]:
        """Match content against labels list of (needle, label) tuples."""
        lowered = content.lower()
        # 先检查自定义翻译
        for needle, label in labels:
            if needle in lowered:
                # 检查是否有用户自定义翻译覆盖
                if content in self._custom_translations:
                    return self._custom_translations[content]
                return label
        return None

    def _connect_signal(self, signal, slot):
        """统一连接信号，自动记录以便断开"""
        conn = signal.connect(slot)
        self._signal_connections.append((signal, slot))
        return conn

    def run(self):
        self._db_conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._db_conn.execute("PRAGMA journal_mode=WAL")
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
        # 先断开所有信号连接
        for signal, slot in self._signal_connections:
            try:
                signal.disconnect(slot)
            except Exception:
                pass
        self._signal_connections.clear()
        # 然后停止定时器等
        self.running = False
        if self._db_conn:
            self._db_conn.close()
            self._db_conn = None

    def set_selected_agent(self, selected_agent: str):
        self._instance_id = selected_agent or self.GLOBAL_AGENT_OPTION

    def get_instance_id(self) -> str:
        """Getter for instance_id - expose to external code"""
        return self._instance_id

    def set_session_selection(self, session_mode: str, selected_session_id: str):
        self.session_mode = session_mode or DEFAULT_SESSION_MODE
        self.selected_session_id = selected_session_id or DEFAULT_SESSION_AUTO

    def get_status_snapshot(self) -> Tuple[str, str, dict]:
        return self._check_status()
        
    def _log_debug_error(self, source: str, error: Exception, **extra) -> None:
        metadata = {
            "health_level": "error",
            "status_reason": f"{source}_error",
            "error": str(error),
            **extra,
        }
        self._append_pet_debug_log(self.ERROR, f"{source} failed: {error}", metadata)

    def _update_token_stats(self) -> None:
        conn = self._db_conn
        if conn is None:
            return
        try:
            conn.row_factory = sqlite3.Row
            filter_info = self._resolve_session_filter(conn)
            session, session_meta = self._get_recent_cli_session(conn, filter_info)
            if not session:
                return
            session_dict = dict(session)
            total_tokens = (
                (session_dict.get('input_tokens') or 0)
                + (session_dict.get('output_tokens') or 0)
                + (session_dict.get('reasoning_tokens') or 0)
            )
            self.performance.update({
                "total_tokens": total_tokens,
                "input_tokens": session_dict.get('input_tokens', 0) or 0,
                "output_tokens": session_dict.get('output_tokens', 0) or 0,
                "reasoning_tokens": session_dict.get('reasoning_tokens', 0) or 0,
                "message_count": session_dict.get('message_count', 0) or 0,
                "token_data_available": total_tokens > 0,
                "resolved_session_id": session_meta.get('resolved_session_id'),
            })
        except Exception as e:
            self._log_debug_error("update_token_stats", e)

    def _track_terminal_activity(self, live_activity: Dict[str, Any]) -> None:
        activity = str((live_activity or {}).get("live_activity") or "")
        detail = str((live_activity or {}).get("live_detail") or "")
        if "terminal command running" in activity.lower() or detail.startswith("正在执行终端命令"):
            self._terminal_activity_hold_until = time.time() + TERMINAL_ACTIVITY_HOLD_SEC
            self._terminal_activity_detail = detail or activity

    def _should_hold_terminal_activity(self, metadata: Dict[str, Any]) -> bool:
        if time.time() > self._terminal_activity_hold_until:
            return False
        recent_live = metadata.get("recent_live_activity") or []
        recent_activity = metadata.get("recent_activity") or []
        combined = [str(item) for item in list(recent_live) + list(recent_activity)]
        if any("模型响应已完成" in item or "已执行 shell 命令" in item or "已完成" in item for item in combined):
            return False
        return bool(self._terminal_activity_detail)

    def _check_status(self) -> Tuple[str, str, dict]:
        metadata = {
            "instance": self._instance_id,
            "selected_agent": self._instance_id,
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
            self._track_terminal_activity(live_activity)
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
            if self._should_hold_terminal_activity(merged) and session_status[0] in {self.WAITING, self.IDLE}:
                merged["status"] = self.WORKING
                merged["status_reason"] = "terminal_activity_hold"
                merged["live_detail"] = self._terminal_activity_detail
                merged["health_level"] = "yellow"
                return self.WORKING, self._terminal_activity_detail, merged
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
            job_name = metadata.get("cron_name") or ""
            return self.WAITING, f"自动推进待命 · 下次 {next_display}·{job_name}", metadata
        metadata['health_level'] = 'yellow'
        return self.WAITING, "等待指令", metadata
    
    def _check_gateway(self) -> Tuple[bool, dict]:
        """检查网关状态"""
        gateway_file = self.hermes_dir / "gateway_state.json"
        try:
            if gateway_file.exists():
                data = json.loads(gateway_file.read_text())
                is_running = data.get("gateway_state") == "running"
                result = {
                    "active_agents": data.get("active_agents", 0),
                    "platforms": data.get("platforms", {}),
                }
                self._gateway_status_cache = {
                    "checked_at": time.time(),
                    "running": is_running,
                    "info": result,
                }
                return is_running, result

            now_ts = time.time()
            cached = self._gateway_status_cache
            if now_ts - cached.get("checked_at", 0.0) < 5.0:
                return cached.get("running", False), dict(cached.get("info", {}))

            result = subprocess.run(
                ["hermes", "gateway", "status"],
                capture_output=True, text=True, timeout=3
            )
            is_running, info = self._parse_gateway_cli_status(result.stdout)
            self._gateway_status_cache = {
                "checked_at": now_ts,
                "running": is_running,
                "info": info,
            }
            return is_running, info
        except Exception as e:
            self._log_debug_error("check_gateway", e)
            return False, {}
    
    def _parse_gateway_cli_status(self, stdout_text: str) -> Tuple[bool, dict]:
        text = (stdout_text or '').strip()
        lowered = text.lower()
        info = {
            "gateway_status_source": "cli",
            "gateway_status_text": text[:160],
        }
        if not lowered:
            return False, info
        if re.search(r'\b(not\s+running|stopped|offline|inactive)\b', lowered):
            return False, info
        if lowered == 'running':
            return True, info
        if re.search(r'\b(gateway_state|status)\s*[:=]\s*running\b', lowered):
            return True, info
        if re.search(r'\bgateway\s+is\s+running\b', lowered):
            return True, info
        return False, info

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
            log_path = self.pet_debug_log_path
            # Rotate if needed
            if log_path.exists():
                lines = log_path.read_text(encoding="utf-8").splitlines()
                if len(lines) >= MAX_DEBUG_LOG_SIZE or log_path.stat().st_size >= MAX_DEBUG_LOG_BYTES:
                    lines = lines[len(lines)//2:]
                    log_path.write_text('\n'.join(lines) + '\n', encoding="utf-8")
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
            with log_path.open("a", encoding="utf-8") as fh:
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
        if age is not None and age > LIVE_ACTIVITY_MAX_AGE_SEC:
            return {}
        activity = str(payload.get("activity") or "").strip()
        tool_name = str(payload.get("current_tool") or "").strip()
        tool_args = payload.get("tool_args") if isinstance(payload.get("tool_args"), dict) else {}
        direct_detail = self._humanize_live_tool_name(tool_name, tool_args, activity)
        detail = direct_detail or chosen_detail

        live_status = self.WAITING
        if payload.get("status") == "working" and (age is None or age <= LIVE_ACTIVITY_FRESH_WORKING_SEC):
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
            if age is not None and age > LIVE_ACTIVITY_YELLOW_AGE:
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

    def _parse_activity_prefix(self, raw: str) -> Tuple[str, str]:
        """Parse activity prefix, returning (prefix_type, content)."""
        if raw.startswith('executing tool: '):
            return ('executing', raw.split(':', 1)[1].strip())
        if raw.startswith('tool completed:'):
            return ('completed', raw.split(':', 1)[1].strip().split('(', 1)[0].strip())
        return ('raw', raw)

    def _match_substring_label(self, content: str, labels: list) -> Optional[str]:
        """Match content against labels list of (needle, label) tuples."""
        lowered = content.lower()
        for needle, label in labels:
            if needle in lowered:
                return label
        return None

    def _safe_args_get(self, args: Dict[str, Any], key: str) -> Any:
        """Safely get value from args dict."""
        return args.get(key) if isinstance(args, dict) else None

    def _format_tool_display(self, tool: str, prefix: str, content: str, args: Dict[str, Any]) -> str:
        """Format tool display name based on prefix type."""
        completed = (prefix == 'completed')
        if tool in tool_registry._action_labels:
            present_label, past_label = tool_registry.get_action_label(tool)
            if tool in ("read_file", "read", "write_file", "write", "patch", "edit"):
                path = self._safe_args_get(args, "path")
                noun = Path(str(path)).name if path else ""
                base = past_label if completed else present_label
                return f"{base}: {noun}" if noun else base
            if tool in ("browser_navigate", "navigate"):
                url = self._safe_args_get(args, "url")
                target = self._extract_target_from_url(str(url)) if url else None
                base = past_label if completed else present_label
                return f"{base}: {target}" if target else base
            return past_label if completed else present_label
        if completed and tool:
            return f"已完成 {tool}"
        if content:
            return content[:64]
        return f"正在执行 {tool}" if tool else "正在处理"

    def _humanize_terminal_activity(self, raw_activity: str) -> str:
        text = (raw_activity or '').strip()
        match = re.search(r'terminal command running \((\d+)s elapsed\)', text, re.IGNORECASE)
        if match:
            return f"正在执行终端命令（{match.group(1)} 秒）"
        return ''

    def _humanize_concurrent_tools(self, raw_activity: str) -> str:
        text = (raw_activity or '').strip()
        match = re.search(r'executing\s+(\d+)\s+tools?\s+concurrently\s*:\s*(.+)$', text, re.IGNORECASE)
        if not match:
            return ''
        count = match.group(1)
        tools_text = match.group(2).strip()
        tool_names = [part.strip() for part in tools_text.split(',') if part.strip()]
        translated = [tool_registry.get_summary_label(name) for name in tool_names[:3]]
        suffix = f" 等{count}个" if tool_names and int(count) > len(tool_names[:3]) else f" {count}个"
        if translated:
            return self._truncate_text(f"正在并发执行{suffix}工具：{', '.join(translated)}", 64)
        return self._truncate_text(f"正在并发执行 {count} 个工具", 64)

    def _humanize_api_call_activity(self, raw_activity: str) -> str:
        text = (raw_activity or '').strip()
        start_match = re.search(r'starting\s+API\s+call\s+#(\d+)', text, re.IGNORECASE)
        if start_match:
            return f"正在请求模型响应 #{start_match.group(1)}"
        complete_match = re.search(r'API\s+call\s+#(\d+)\s+completed', text, re.IGNORECASE)
        if complete_match:
            return f"模型响应已完成 #{complete_match.group(1)}"
        return ''

    def _humanize_live_tool_name(self, tool_name: str, args: Dict[str, Any], activity: str = "") -> str:
        tool = str(tool_name or "").strip()
        raw_activity = str(activity or "").strip()
        prefix_type, parsed_content = self._parse_activity_prefix(raw_activity)
        if prefix_type in {'executing', 'completed'}:
            tool = parsed_content

        terminal_summary = self._humanize_terminal_activity(raw_activity)
        if terminal_summary:
            return terminal_summary

        concurrent_summary = self._humanize_concurrent_tools(raw_activity)
        if concurrent_summary:
            return concurrent_summary

        api_summary = self._humanize_api_call_activity(raw_activity)
        result = self._format_tool_display(tool, prefix_type, raw_activity, args)
        matched_label = self._match_substring_label(raw_activity, LIVE_ACTIVITY_SUBSTRING_LABELS)

        if api_summary:
            return api_summary
        if 'API error recovery' in raw_activity:
            return '模型响应异常，正在重试'
        if matched_label and matched_label == '正在接收模型响应':
            return matched_label
        if matched_label and (not tool or result == raw_activity[:64] or result == raw_activity or result in LOW_INFORMATION_STATUS_TEXTS):
            return matched_label
        if matched_label and not result:
            return matched_label
        # 未找到翻译时记录原文
        if not matched_label and not api_summary and not concurrent_summary:
            save_unknown_translation(raw_activity, "live_activity")
        return result or matched_label

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

        now = datetime.now()
        future_jobs = []
        for job in pool:
            next_dt = self._parse_timestamp(job.get("next_run_at"))
            if next_dt and next_dt >= now:
                future_jobs.append((next_dt, job))
        if future_jobs:
            future_jobs.sort(key=lambda item: item[0])
            return future_jobs[0][1]

        def score(job: Dict[str, Any]):
            parsed = self._parse_timestamp(job.get("last_run_at") or job.get("created_at"))
            return parsed or datetime.min

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

        job_state = job.get("state")
        next_dt = self._parse_timestamp(job.get("next_run_at"))
        overdue = False
        if next_dt and job_state == "scheduled" and job.get("enabled", True):
            overdue = (datetime.now() - next_dt).total_seconds() > 180

        # Paused jobs should not show a next-run time
        if job_state == "paused":
            next_dt = None

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
            # 白名单：只允许 /Users/xxx/ 路径且后跟合法文件扩展名，防止正则注入
            allowed_exts = r'\.(txt|pdf|png|jpg|jpeg|gif|mp3|mp4|doc|docx|xls|xlsx|ppt|pptx|zip|tar|gz|log|json|xml|html|css|js|py|sh|md|pyc|webp|bmp|ico|tiff|tif|heic|heif|svg|jsonl|csv|tsv|yaml|yml|toml|ini|conf|cfg)$'
            path_pattern = re.compile(r'(/Users/[\w\-\.]+/[\w\-\./]+' + allowed_exts + r')', re.IGNORECASE)
            path_matches = path_pattern.findall(content)
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

        # 从配置读取关键词列表 (M8: 支持通用+项目专用关键词)
        all_keywords = SCORE_KEYWORDS.get('generic', []) + SCORE_KEYWORDS.get('chat_stock', [])

        positive_tokens = {
            "还差": 8,
            "继续": 4,
            "已完成": 8,
            "完成": 4,
            "修": 3,
            "补": 3,
            "记录": 3,
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
        # 动态添加配置中的关键词
        for kw in all_keywords:
            if kw not in positive_tokens:
                positive_tokens[kw] = 4  # 默认权重
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
        if lowered.startswith("<think>") or lowered.startswith("<thinking>"):
            return "思考中…"
        if text.startswith("你好") or text.startswith("老板") or text.startswith("您好"):
            return "Hermes 已回复"
        best_line = self._pick_salient_text_line(text)
        if not best_line:
            return ""
        lowered_best = best_line.lower()
        if lowered_best.startswith("<think>") or lowered_best.startswith("<thinking>"):
            return "思考中…"
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
            if content_text.startswith("<think>") or content_text.startswith("<thinking>"):
                return "思考中…"
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
        return tool_registry.get_browser_label(tool_name)

    def _compose_tool_summary(self, tool_name: str, target: str, error_state: bool = False, call_count: int = 1) -> str:
        prefix = "❌" if error_state else self._tool_emoji(tool_name)
        if tool_name.startswith("browser_"):
            label = self._browser_action_label(tool_name)
            summary = f"{prefix} {label}"
            if target:
                summary += f" {target}"
        else:
            label = tool_registry.get_summary_label(tool_name)
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

        # Tools with special handling
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

        # Generic key-based extraction
        key = TOOL_TARGET_KEYS.get(tool_name)
        if key:
            value = args.get(key) if isinstance(args, dict) else None
            if isinstance(value, str) and value.strip():
                if tool_name in TOOL_PATH_KEYS:
                    return self._shorten_path(value)
                if tool_name in TOOL_URL_KEYS:
                    return self._extract_target_from_url(value)
                if tool_name in TOOL_PATTERN_KEYS:
                    return self._format_pattern_target(value, 42)
                return self._truncate_text(value.strip(), TOOL_TRUNCATE.get(tool_name, 40))

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

        if activity in LOW_INFORMATION_STATUS_TEXTS:
            activity = ""

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

        # 使用 tool_registry 获取 browser 标签
        if tool_registry.get_browser_label(tool_name) != "操作页面":
            present_label, past_label = tool_registry.get_action_label(tool_name)
            action = present_label if status == self.WORKING else past_label
            summary = f"正在{action}" if status == self.WORKING else f"刚{action}"
            if target:
                summary += f" {target}"
            if call_count > 1:
                summary += f" +{call_count - 1}"
            return self._truncate_text(summary.strip(), 48)

        # 使用 tool_registry 获取通用动词
        present, past = tool_registry.get_verb_pair(tool_name)

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
        live_cache = self._live_session_cache
        seen_paths = set()
        try:
            for session_file in self.sessions_dir.glob("session_*.json"):
                cache_key = str(session_file)
                seen_paths.add(cache_key)
                try:
                    stat = session_file.stat()
                    cached = live_cache.get(cache_key)
                    if cached and cached[0] == stat.st_mtime:
                        payload = cached[1]
                        live_cache.move_to_end(cache_key)
                    else:
                        payload = json.loads(session_file.read_text())
                        live_cache[cache_key] = (stat.st_mtime, payload)
                        if len(live_cache) > self._MAX_CACHE_ENTRIES:
                            live_cache.popitem(last=False)
                except Exception as e:
                    self._log_debug_error("list_live_cli_sessions", e, session_file=cache_key)
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
                last_ts = last_dt.timestamp() if last_dt else stat.st_mtime
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
        except Exception as e:
            self._log_debug_error("list_live_cli_sessions", e)
            return []

        stale_keys = [key for key in live_cache.keys() if key not in seen_paths]
        for key in stale_keys:
            live_cache.pop(key, None)

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
        except Exception as e:
            self._log_debug_error("load_live_session_messages", e, session_id=session_id)
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
        effective_selected = self._instance_id or self.GLOBAL_AGENT_OPTION
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
        except Exception as e:
            self._log_debug_error("get_available_agents", e)
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
        except Exception as e:
            self._log_debug_error("get_available_sessions", e)
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

        conn = self._db_conn
        if conn is None:
            return None
        try:
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

            if last_age is not None and last_age > LIVE_ACTIVITY_RED_AGE:
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
            self._log_debug_error("database_query", e)
            return None

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
        except Exception as e:
            self._log_debug_error("get_recent_history", e)
            return []
        finally:
            if conn:
                conn.close()

    def get_active_sessions(self, exclude_session_id: str = None, max_age_minutes: int = 5) -> List[Dict]:
        """检测最近活跃的会话（非当前会话），用于多会话指示器"""
        if not self.db_path.exists():
            return []
        conn = None
        try:
            from datetime import timedelta
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            cutoff = (datetime.now() - timedelta(minutes=max_age_minutes)).isoformat()
            rows = conn.execute("""
                SELECT s.id, s.started_at,
                    COALESCE(MAX(m.timestamp), s.started_at) AS last_active,
                    (
                        SELECT role
                        FROM messages
                        WHERE session_id = s.id
                        ORDER BY timestamp DESC
                        LIMIT 1
                    ) AS last_role
                FROM sessions s
                LEFT JOIN messages m ON m.session_id = s.id
                WHERE s.source = 'cli'
                GROUP BY s.id
                HAVING COALESCE(MAX(m.timestamp), s.started_at) > ?
                ORDER BY last_active DESC
                LIMIT 8
            """, [cutoff]).fetchall()
            result = []
            for row in rows:
                sid = str(row['id'])
                if exclude_session_id and sid == exclude_session_id:
                    continue
                if str(row['last_role'] or '') == 'user':
                    continue
                age = self._message_age_seconds(row['last_active'])
                status = 'working' if (age is not None and age < 30) else 'waiting'
                result.append({
                    'session_id': sid,
                    'label': self._format_session_label(dict(row)),
                    'status': status,
                    'last_active': row['last_active'],
                })
            return result
        except Exception as e:
            self._log_debug_error("get_active_sessions", e, exclude_session_id=exclude_session_id)
            return []
        finally:
            if conn:
                conn.close()


# ============================================================
# macOS 通知 (使用 UserNotifications - modern API)
# ============================================================
def send_macos_notification(title: str, message: str, sound: bool = True):
    """Send macOS notification via UNUserNotificationCenter (modern API,取代废弃的NSUserNotification)."""
    if objc is None or UN_AVAILABLE:
        return

    try:
        center = UserNotifications.UserNotificationCenter.currentNotificationCenter()
        content = UserNotifications.UserNotificationContent.new()
        content.setTitle_(title)
        content.setSubtitle_("")
        content.setBody_(message)
        if sound:
            content.setSoundName_(UserNotifications.UNDefaultNotificationSoundName)
        else:
            content.setSoundName_(None)
        center.deliverNotification_(content)
    except Exception as e:
        print(f"Notification error: {e}", file=sys.stderr)


def save_unknown_translation(raw: str, context: str = "live_activity"):
    """将未翻译的原始字符串记录到 JSON 文件"""
    if not raw or len(raw) < 3:
        return

    built_in_translation = None
    lowered = raw.lower()
    terminal_match = re.search(r'terminal command running \((\d+)s elapsed\)', lowered, re.IGNORECASE)
    if terminal_match:
        built_in_translation = f"正在执行终端命令（{terminal_match.group(1)} 秒）"
    elif "waiting for stream response" in lowered:
        built_in_translation = "正在等待模型响应"
    elif "receiving stream response" in lowered:
        built_in_translation = "正在接收模型响应"

    # 过滤掉明显是日志/调试内容的
    skip_patterns = ("#", "api call #", "tool completed:", "executing tool:", "/", "http", ".hermes")
    if any(p in lowered for p in skip_patterns) and not built_in_translation:
        return
    try:
        Path(UNKNOWN_TRANSLATIONS_FILE).parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if Path(UNKNOWN_TRANSLATIONS_FILE).exists():
            try:
                data = json.loads(Path(UNKNOWN_TRANSLATIONS_FILE).read_text())
            except Exception:
                data = {}
        # 用 (context, raw) 作为 key，避免不同来源的同一字符串互相覆盖
        key = f"{context}:{raw}"
        if key not in data:
            data[key] = {"raw": raw, "context": context, "translation": built_in_translation or ""}
            Path(UNKNOWN_TRANSLATIONS_FILE).write_text(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception:
        pass


def play_sound(sound_name: str = "Glass"):
    if not SOUND_AVAILABLE:
        return
    
    try:
        sound = NSSound.soundNamed_(sound_name)
        if sound:
            sound.play()
    except Exception:
        pass


