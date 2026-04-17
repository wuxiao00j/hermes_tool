"""Backward compatibility: re-export all public symbols from the split modules."""
from config import *
from monitor import *
from ui import *

# Convenience re-exports for the most common symbols
try:
    from config import ThemeConfig, THEMES, Theme, DEFAULT_STATUS_COLORS
    from monitor import ConfigManager, HermesMonitor
    from ui import HermesDesktopPet, DynamicIslandWidget, main
except ImportError:
    pass
