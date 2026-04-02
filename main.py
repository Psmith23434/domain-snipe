import sys
import re
import csv
import time
import threading
import webbrowser
from collections import deque
from datetime import datetime, timezone

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QSystemTrayIcon, QMenu,
    QTextEdit, QLabel, QFileDialog, QTabWidget, QGroupBox, QMessageBox,
    QComboBox, QTimeEdit, QCheckBox, QSpinBox, QSplitter, QProgressBar,
    QFrame, QFormLayout, QAbstractItemView
)
from PyQt5.QtCore import Qt, QTimer, QTime
from PyQt5.QtGui import QColor, QFont, QPalette

from sniper import snipe_domain, POLL_MODES, set_priority_enabled, update_domain_row
from api import check_domain, register_domain

from constants import (
    TLD_PRICES, DROP_TIMES_TABLE,
    COL_DRAG, COL_SNIPE, COL_DOMAIN, COL_DROP, COL_PRICE,
    COL_WHOIS, COL_STATUS, COL_NEXT, COL_ACT,
    MONITOR_MIN_PER_DOMAIN_INTERVAL, MONITOR_MAX_USER_RPS_DELAY,
    MONITOR_IDLE_SLEEP, WHOIS_MIN_SPACING,
)
from utils import (
    normalize_domain, get_tld_price, get_drop_window,
    estimate_drop_date, _extract_expiry_from_raw_whois, _first_datetime, _norm_status,
)
from persistence import load_watchlist, save_watchlist, load_settings, save_settings, \
    load_rampage_queue, save_rampage_queue
from widgets import DraggableTable, Signals, _divider, _section_label

# ── Mixin imports ─────────────────────────────────────────────────────────────
from mixin_builders  import UiBuildersMixin
from mixin_tables    import UiTablesMixin
from mixin_monitor   import MonitorMixin
from mixin_actions   import ActionsMixin
from mixin_handlers  import HandlersMixin
# ─────────────────────────────────────────────────────────────────────────────

class DropCatcher(
    UiBuildersMixin,
    UiTablesMixin,
    MonitorMixin,
    ActionsMixin,
    HandlersMixin,
    QWidget,
):
    """
    Domain drop-catcher UI.  All methods live in the five mixin files;
    only __init__ (wiring) and closeEvent (shutdown) remain here.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎯 Domain Drop Catcher v2.3 - Spaceship")
        self.resize(1360, 840)

        self.monitor_rows = {}
        self.rampage_rows = {}
        self.monitor_next_ts = {}
        self.rampage_next_ts = {}
        self.caught = []
        self.settings = load_settings()
        self._LOG_MAX_LINES = 500

        self._stop_events = {}
        self._sched_armed_for_minute = None

        self.monitor_runtime = {}
        self.monitor_scheduler_lock = threading.Lock()
        self.monitor_scheduler_wake = threading.Event()
        self.monitor_scheduler_stop = threading.Event()
        self.monitor_global_backoff_until = 0.0
        self.monitor_last_request_ts = 0.0

        self.whois_queue_lock = threading.Lock()
        self.whois_queue = deque()  # deque: O(1) popleft() in the WHOIS worker thread
        self.whois_pending = set()
        self.whois_worker_wake = threading.Event()
        self.whois_worker_stop = threading.Event()
        self.whois_last_request_ts = 0.0

        self.signals = Signals()
        self.signals.status_update.connect(self._update_status)
        self.signals.success.connect(self._handle_success)
        self.signals.failure.connect(self._handle_failure)
        self.signals.whois_result.connect(self._show_whois_result)
        self.signals.premium_detect.connect(self._handle_premium)
        self.signals.next_check.connect(self._store_next_check)
        self.signals.price_update.connect(self._update_price_col)
        self.signals.premium_check_result.connect(self._show_premium_result)

        self.countdown_timer = QTimer()
        self.countdown_timer.timeout.connect(self._tick_countdowns)
        self.countdown_timer.start(1000)

        self.whois_timer = QTimer()
        self.whois_timer.timeout.connect(self._auto_whois_tick)

        self.whois_countdown_timer = QTimer()
        self.whois_countdown_timer.timeout.connect(self._tick_whois_countdown)
        self.whois_remaining = 0
        self.whois_interval_secs = 60

        self.sched_timer = QTimer()
        self.sched_timer.timeout.connect(self._check_scheduled)
        self.sched_timer.start(1000)

        self._build_ui()
        self._setup_tray()
        self._apply_settings()

        for d in load_watchlist():
            self._add_monitor_row(d)
        for d in self._load_rampage_queue():
            self._add_rampage_row(d)

        self.monitor_scheduler_thread = threading.Thread(
            target=self._monitor_scheduler_loop,
            name="monitor-scheduler",
            daemon=True,
        )
        self.monitor_scheduler_thread.start()

        self.whois_worker_thread = threading.Thread(
            target=self._whois_worker_loop,
            name="whois-worker",
            daemon=True,
        )
        self.whois_worker_thread.start()

    def closeEvent(self, event):
        # 1. Stop all individual domain stop_events (monitor & rampage)
        for stop_event in self._stop_events.values():
            stop_event.set()

        # 2. Stop the monitor scheduler thread
        self.monitor_scheduler_stop.set()
        self.monitor_scheduler_wake.set()  # wake it so it sees the stop immediately

        # 3. Stop the WHOIS worker thread
        self.whois_worker_stop.set()
        self.whois_worker_wake.set()  # wake it so it sees the stop immediately

        # 4. Stop all QTimers
        self.countdown_timer.stop()
        self.sched_timer.stop()
        self.whois_timer.stop()
        self.whois_countdown_timer.stop()

        # 5. Save state before exiting
        save_watchlist([
            self.monitor_table.item(r, COL_DOMAIN).text()
            for r in range(self.monitor_table.rowCount())
            if self.monitor_table.item(r, COL_DOMAIN)
        ])
        save_settings(self.settings)

        # 6. Give threads a short moment to finish, then allow close
        self.monitor_scheduler_thread.join(timeout=2)
        self.whois_worker_thread.join(timeout=2)

        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    pal = QPalette()
    pal.setColor(QPalette.Window, QColor("#0f172a"))
    pal.setColor(QPalette.WindowText, QColor("#e2e8f0"))
    pal.setColor(QPalette.Base, QColor("#111827"))
    pal.setColor(QPalette.AlternateBase, QColor("#1e293b"))
    pal.setColor(QPalette.ToolTipBase, QColor("#111827"))
    pal.setColor(QPalette.ToolTipText, QColor("#e2e8f0"))
    pal.setColor(QPalette.Text, QColor("#e2e8f0"))
    pal.setColor(QPalette.Button, QColor("#1e293b"))
    pal.setColor(QPalette.ButtonText, QColor("#e2e8f0"))
    pal.setColor(QPalette.BrightText, QColor("#ffffff"))
    pal.setColor(QPalette.Highlight, QColor("#7c3aed"))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    app.setPalette(pal)

    w = DropCatcher()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
