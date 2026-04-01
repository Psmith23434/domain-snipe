# mixin_builders.py
# All _build_* / _setup_domain_table methods for DropCatcher.
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QTextEdit, QLabel,
    QTabWidget, QGroupBox, QComboBox, QTimeEdit, QCheckBox, QSpinBox,
    QSplitter, QProgressBar, QFrame, QFormLayout, QAbstractItemView,
    QMessageBox,
)
from PyQt5.QtCore import Qt, QTimer, QTime

from sniper import POLL_MODES
from constants import (
    TLD_PRICES, DROP_TIMES_TABLE,
    COL_DRAG, COL_SNIPE, COL_AUTOBUY, COL_DOMAIN,
    COL_DROP, COL_PRICE, COL_WHOIS, COL_STATUS, COL_NEXT, COL_ACT,
)
from utils import get_tld_price, get_drop_window
from widgets import DraggableTable, Signals, _divider, _section_label


class UiBuildersMixin:
    """Mixin: all UI-construction (_build_* / _setup_domain_table) methods."""

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        root.addWidget(self._build_header())

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setUsesScrollButtons(True)
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border:none; background:#0f172a; }
            QTabBar::tab {
                background:#1e293b; color:#94a3b8; padding:10px 20px; min-width:150px;
                border-radius:6px 6px 0 0; margin-right:3px; font-size:12px; font-weight:600;
            }
            QTabBar::tab:selected { background:#7c3aed; color:white; }
            QTabBar::tab:hover { background:#334155; color:#e2e8f0; }
        """)
        root.addWidget(self.tabs)

        self.tabs.addTab(self._build_sniper_tab(),    "\U0001f3af Sniper")
        self.tabs.addTab(self._build_whois_tab(),     "\U0001f50e WHOIS Monitor")
        self.tabs.addTab(self._build_ai_tab(),        "\U0001f916 AI Filter")
        self.tabs.addTab(self._build_portfolio_tab(), "\U0001f4e6 Portfolio")
        self.tabs.addTab(self._build_info_tab(),      "\U0001f552 Drop Times")
        self.tabs.addTab(self._build_settings_tab(),  "\u2699\ufe0f Settings")

        root.addWidget(self._build_footer())

    def _build_header(self):
        h = QFrame()
        h.setFixedHeight(48)
        h.setStyleSheet(
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #1e1b4b,stop:0.5 #312e81,stop:1 #1e1b4b);"
        )
        hl = QHBoxLayout(h)
        hl.setContentsMargins(16, 0, 16, 0)

        title = QLabel("\U0001f3af Domain Drop Catcher v2.3 - Spaceship API")
        title.setStyleSheet("color:white;font-size:15px;font-weight:bold;")

        self.clock_lbl = QLabel()
        self.clock_lbl.setStyleSheet("color:#94a3b8;font-family:Consolas,monospace;font-size:12px;")

        ct = QTimer(self)
        ct.timeout.connect(self._update_clock)
        ct.start(1000)
        self._update_clock()

        hl.addWidget(title)
        hl.addStretch()
        hl.addWidget(self.clock_lbl)
        return h

    def _build_footer(self):
        f = QFrame()
        f.setFixedHeight(22)
        f.setStyleSheet("background:#0f172a;border-top:1px solid #1e293b;")
        fl = QHBoxLayout(f)
        fl.setContentsMargins(10, 0, 10, 0)

        self.footer_lbl = QLabel("Ready.")
        self.footer_lbl.setStyleSheet("color:#475569;font-size:10px;")
        fl.addWidget(self.footer_lbl)
        fl.addStretch()
        return f

    def _build_sniper_tab(self):
        w = QWidget()
        sl = QVBoxLayout(w)
        sl.setSpacing(6)

        self.sniper_tabs = QTabWidget()
        self.sniper_tabs.setDocumentMode(True)
        self.sniper_tabs.setStyleSheet("""
            QTabWidget::pane { border:1px solid #1e293b; background:#0f172a; }
            QTabBar::tab {
                background:#172033; color:#94a3b8; padding:8px 16px; min-width:160px;
                border-radius:6px 6px 0 0; margin-right:2px; font-size:12px; font-weight:600;
            }
            QTabBar::tab:selected { background:#4c1d95; color:white; }
            QTabBar::tab:hover { background:#24324a; color:#e2e8f0; }
        """)

        self.sniper_tabs.addTab(self._build_monitoring_page(), "\U0001f4e1 Monitoring")
        self.sniper_tabs.addTab(self._build_rampage_page(),    "\u26a1 Rampage Queue")
        sl.addWidget(self.sniper_tabs)

        sl.addWidget(_section_label("\U0001f4cb Activity Log"))
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(110)
        self.log.setStyleSheet("background:#111827;color:#34d399;font-family:Consolas,monospace;font-size:11px;")
        sl.addWidget(self.log)
        return w

    def _build_monitoring_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(6)

        # Filter bar
        search_row = QHBoxLayout()
        self.monitor_search = QLineEdit(placeholderText="\U0001f50e Filter monitored domains...")
        self.monitor_search.textChanged.connect(self._filter_monitor_table)
        self.monitor_search.setStyleSheet("padding:6px 10px;border-radius:5px;")
        search_row.addWidget(self.monitor_search)
        layout.addLayout(search_row)

        # Domain input + action buttons
        input_row = QHBoxLayout()
        self.input = QLineEdit(placeholderText="\u2795 Add a domain to monitoring (e.g. coolbrand.com) and press Enter")
        self.input.returnPressed.connect(self.add_domain)
        input_row.addWidget(self.input)

        self.start_monitor_btn = QPushButton("\U0001f3af Start Monitoring")
        self.start_monitor_btn.clicked.connect(self.start_checked_monitoring)
        self.start_monitor_btn.setToolTip("Start queued Layer 1 monitoring for checked domains")
        input_row.addWidget(self.start_monitor_btn)

        self.stop_checked_monitor_btn = QPushButton("\u23f9 Stop Checked")
        self.stop_checked_monitor_btn.clicked.connect(self.stop_checked_monitoring)
        self.stop_checked_monitor_btn.setToolTip("Stop monitoring for checked domains")
        input_row.addWidget(self.stop_checked_monitor_btn)

        self.stop_all_monitor_btn = QPushButton("\U0001f6d1 Stop All")
        self.stop_all_monitor_btn.clicked.connect(self.stop_all_monitoring)
        self.stop_all_monitor_btn.setToolTip("Stop monitoring for all domains without removing them")
        input_row.addWidget(self.stop_all_monitor_btn)

        for label, slot, tip in [
            ("\u2795 Add",             self.add_domain,   "Add a single domain to monitoring"),
            ("\U0001f4e5 Import .txt", self.import_txt,   "Load one domain per line from a .txt file"),
            ("\U0001f50d WHOIS All",   self.bulk_whois,   "Run WHOIS on every monitored domain"),
            ("\U0001f4e4 Export CSV",  self.export_csv,   "Save caught domains to CSV"),
        ]:
            b = QPushButton(label)
            b.clicked.connect(slot)
            b.setToolTip(tip)
            input_row.addWidget(b)

        layout.addLayout(input_row)

        # ── Selection + Auto-Buy bulk controls (ABOVE global toggle) ─────
        bulk_row = QHBoxLayout()
        bulk_row.setSpacing(6)

        # Selection group
        lbl_sel = QLabel("\u2713 Selection:")
        lbl_sel.setStyleSheet("color:#64748b;font-size:11px;")
        bulk_row.addWidget(lbl_sel)

        btn_ca = QPushButton("\u2611 Check All")
        btn_ca.setFixedHeight(24)
        btn_ca.setStyleSheet("font-size:11px;padding:2px 8px;")
        btn_ca.setToolTip("Check all domains in the monitoring table")
        btn_ca.clicked.connect(self.check_all_monitor)
        bulk_row.addWidget(btn_ca)

        btn_ua = QPushButton("\u2610 Uncheck All")
        btn_ua.setFixedHeight(24)
        btn_ua.setStyleSheet("font-size:11px;padding:2px 8px;")
        btn_ua.setToolTip("Uncheck all domains in the monitoring table")
        btn_ua.clicked.connect(self.uncheck_all_monitor)
        bulk_row.addWidget(btn_ua)

        bulk_row.addWidget(_divider())

        # Auto-Buy arm group
        lbl_ab = QLabel("\U0001f3af Auto-Buy:")
        lbl_ab.setStyleSheet("color:#fbbf24;font-size:11px;font-weight:bold;")
        bulk_row.addWidget(lbl_ab)

        btn_arm = QPushButton("\U0001f3af Arm All")
        btn_arm.setFixedHeight(24)
        btn_arm.setStyleSheet("font-size:11px;padding:2px 8px;color:#fbbf24;")
        btn_arm.setToolTip("Enable the Auto-Buy column for every domain in the monitoring table")
        btn_arm.clicked.connect(self._arm_all_autobuy)
        bulk_row.addWidget(btn_arm)

        btn_disarm = QPushButton("\U0001f6ab Disarm All")
        btn_disarm.setFixedHeight(24)
        btn_disarm.setStyleSheet("font-size:11px;padding:2px 8px;")
        btn_disarm.setToolTip("Disable the Auto-Buy column for every domain in the monitoring table")
        btn_disarm.clicked.connect(self._disarm_all_autobuy)
        bulk_row.addWidget(btn_disarm)

        bulk_row.addStretch()
        layout.addLayout(bulk_row)
        # ────────────────────────────────────────────────────────────────

        # ── Global Auto-Buy toggle (BELOW bulk controls) ─────────────────
        autobuy_row = QHBoxLayout()
        autobuy_row.setSpacing(8)

        self.auto_buy_chk = QCheckBox("\u26a0\ufe0f Enable Auto-Buy")
        self.auto_buy_chk.setChecked(False)
        self.auto_buy_chk.setToolTip(
            "HIGH RISK \u2014 GLOBAL MASTER SWITCH.\n"
            "When ON, domains whose \U0001f3af column is also checked\n"
            "will be purchased automatically when they become available.\n"
            "Both this AND the per-row \U0001f3af must be ON for any purchase to happen."
        )
        self.auto_buy_chk.setStyleSheet(
            "QCheckBox { color:#fbbf24; font-weight:bold; font-size:12px; padding:4px 8px; }"
            "QCheckBox::indicator { width:16px; height:16px; }"
            "QCheckBox::indicator:unchecked { border:2px solid #475569; border-radius:3px; background:#1e293b; }"
            "QCheckBox::indicator:checked   { border:2px solid #ef4444; border-radius:3px; background:#ef4444; }"
        )
        self.auto_buy_chk.toggled.connect(self._on_auto_buy_toggled)

        self.auto_buy_warning_lbl = QLabel()
        self.auto_buy_warning_lbl.setStyleSheet(
            "color:#ef4444; font-weight:bold; font-size:11px; padding:2px 6px;"
            "background:#450a0a; border:1px solid #7f1d1d; border-radius:4px;"
        )
        self.auto_buy_warning_lbl.setVisible(False)

        autobuy_row.addWidget(self.auto_buy_chk)
        autobuy_row.addWidget(self.auto_buy_warning_lbl)
        autobuy_row.addStretch()
        layout.addLayout(autobuy_row)
        # ────────────────────────────────────────────────────────────────

        # Monitoring Controls group box
        controls = QGroupBox("\U0001f4e1 Monitoring Controls")
        controls.setStyleSheet(
            "QGroupBox{color:#94a3b8;font-size:11px;border:1px solid #1e293b;border-radius:6px;margin-top:4px;padding:4px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:8px;}"
        )
        bar = QHBoxLayout(controls)
        bar.setSpacing(10)

        bar.addWidget(QLabel("Interval:"))
        self.poll_mode = QComboBox()
        monitor_modes = [m for m in POLL_MODES.keys() if "Rampage" not in m]
        self.poll_mode.addItems(monitor_modes)
        self.poll_mode.setCurrentText("Normal (60s)" if "Normal (60s)" in monitor_modes else monitor_modes[0])
        self.poll_mode.currentTextChanged.connect(self._on_poll_mode_changed)
        bar.addWidget(self.poll_mode)

        self.custom_secs = QSpinBox()
        self.custom_secs.setRange(1, 3600)
        self.custom_secs.setValue(15)
        self.custom_secs.setSuffix("s")
        self.custom_secs.setVisible(False)
        self.custom_secs.valueChanged.connect(lambda *_: self._wake_monitor_scheduler())
        bar.addWidget(self.custom_secs)

        self.mode_badge = QLabel("\U0001f7e2 Normal (60s)")
        self.mode_badge.setStyleSheet("color:#4ade80;font-weight:bold;padding:0 8px;")
        bar.addWidget(self.mode_badge)

        bar.addWidget(_divider())

        self.auto_stop = QSpinBox()
        self.auto_stop.setRange(0, 24)
        self.auto_stop.setValue(0)
        self.auto_stop.setSuffix("h auto-stop")
        self.auto_stop.setToolTip("0 disables auto-stop. Otherwise, newly started monitors stop after N hours.")
        bar.addWidget(self.auto_stop)

        bar.addWidget(_divider())

        self.monitor_delay_label = QLabel("Queue: idle")
        self.monitor_delay_label.setStyleSheet("color:#93c5fd;font-weight:bold;padding:0 8px;")
        bar.addWidget(self.monitor_delay_label)

        bar.addStretch()
        layout.addWidget(controls)

        # Table
        self.monitor_table = QTableWidget(0, 10)
        self._setup_domain_table(self.monitor_table, draggable=False)
        self.monitor_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.monitor_table.customContextMenuRequested.connect(
            lambda pos: self._context_menu(self.monitor_table, pos, "monitor")
        )
        layout.addWidget(self.monitor_table)

        self.monitor_stats_label = QLabel("\U0001f4e1 Monitoring domains: 0 | Active: 0")
        self.monitor_stats_label.setStyleSheet("color:#475569;font-size:11px;padding:2px 4px;")
        layout.addWidget(self.monitor_stats_label)

        return page

    def _on_auto_buy_toggled(self, checked):
        if checked:
            reply = QMessageBox.warning(
                self,
                "\u26a0\ufe0f HIGH RISK \u2014 Enable Auto-Buy?",
                "<b style='color:#ef4444;font-size:14px;'>\u26a0\ufe0f WARNING: Auto-Buy is a HIGH RISK feature.</b><br><br>"
                "When enabled, domains with the <b>\U0001f3af column checked</b> will be "
                "<b>purchased IMMEDIATELY and AUTOMATICALLY</b> when they become available.<br><br>"
                "<b>Before enabling, make sure:</b>"
                "<ul>"
                "<li>You have only checked \U0001f3af on domains you <u>actually want to buy</u>.</li>"
                "<li>You understand that registrations <u>cannot be undone or refunded</u>.</li>"
                "</ul>"
                "Do you want to enable Auto-Buy?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                self.auto_buy_chk.blockSignals(True)
                self.auto_buy_chk.setChecked(False)
                self.auto_buy_chk.blockSignals(False)
                return
            self.auto_buy_warning_lbl.setText("\U0001f534 AUTO-BUY ACTIVE \u2014 armed domains will be purchased automatically!")
            self.auto_buy_warning_lbl.setVisible(True)
            self.append_log("[AUTO-BUY] Global switch ON \u2014 armed domains will be registered when available.")
        else:
            self.auto_buy_warning_lbl.setVisible(False)
            self.append_log("[AUTO-BUY] Global switch OFF \u2014 monitor will only check availability.")

    def _build_rampage_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(6)

        info = QLabel(
            "Move only your best targets here. Rows in this table are the Layer 2 queue, and drag order controls Rampage priority."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#94a3b8;font-size:11px;padding:4px 2px;")
        layout.addWidget(info)

        search_row = QHBoxLayout()
        self.rampage_search = QLineEdit(placeholderText="\u26a1 Filter rampage queue...")
        self.rampage_search.textChanged.connect(self._filter_rampage_table)
        self.rampage_search.setStyleSheet("padding:6px 10px;border-radius:5px;")
        search_row.addWidget(self.rampage_search)
        layout.addLayout(search_row)

        input_row = QHBoxLayout()
        self.rampage_input = QLineEdit(placeholderText="\u26a1 Add a domain directly to the Rampage queue")
        self.rampage_input.returnPressed.connect(self.add_rampage_domain)
        input_row.addWidget(self.rampage_input)

        for label, slot, tip in [
            ("\u2795 Add",  self.add_rampage_domain, "Add a domain directly to the Rampage queue"),
            ("\U0001f4e5 Add checked from Monitoring", self.add_checked_to_rampage, "Copy checked monitoring domains into the Rampage queue"),
            ("\u25b6\ufe0f Start Rampage", self.start_rampage_all, "Start Layer 1 + Layer 2 for all queued domains"),
            ("\u23f9 Stop Checked", self.stop_checked_rampage, "Stop checked rampage domains"),
            ("\U0001f6d1 Stop All",  self.stop_all_rampage,    "Stop all rampage domains"),
            ("\U0001f5d1 Clear Queue", self.clear_rampage_queue, "Remove all domains from the Rampage queue"),
        ]:
            b = QPushButton(label)
            b.clicked.connect(slot)
            b.setToolTip(tip)
            input_row.addWidget(b)

        layout.addLayout(input_row)

        # Check All / Uncheck All for Rampage
        rsel_row = QHBoxLayout()
        rsel_row.setSpacing(6)
        rlbl = QLabel("\u2713 Selection:")
        rlbl.setStyleSheet("color:#64748b;font-size:11px;")
        rsel_row.addWidget(rlbl)

        btn_rca = QPushButton("\u2611 Check All")
        btn_rca.setFixedHeight(24)
        btn_rca.setStyleSheet("font-size:11px;padding:2px 8px;")
        btn_rca.setToolTip("Check all domains in the Rampage table")
        btn_rca.clicked.connect(self.check_all_rampage)
        rsel_row.addWidget(btn_rca)

        btn_rua = QPushButton("\u2610 Uncheck All")
        btn_rua.setFixedHeight(24)
        btn_rua.setStyleSheet("font-size:11px;padding:2px 8px;")
        btn_rua.setToolTip("Uncheck all domains in the Rampage table")
        btn_rua.clicked.connect(self.uncheck_all_rampage)
        rsel_row.addWidget(btn_rua)

        rsel_row.addStretch()
        layout.addLayout(rsel_row)

        # Rampage Controls group box
        controls = QGroupBox("\u26a1 Rampage Controls")
        controls.setStyleSheet(
            "QGroupBox{color:#94a3b8;font-size:11px;border:1px solid #1e293b;border-radius:6px;margin-top:4px;padding:4px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:8px;}"
        )
        bar = QHBoxLayout(controls)
        bar.setSpacing(10)

        self.priority_check = QCheckBox("\u2b50 Priority weighting")
        self.priority_check.setToolTip("Row 1 gets 3 queue slots, row 2 gets 2, the rest get 1.")
        self.priority_check.toggled.connect(self._on_priority_toggled)
        bar.addWidget(self.priority_check)

        bar.addWidget(_divider())
        bar.addWidget(QLabel("\U0001f552 Auto-Rampage at:"))

        self.schedule_time = QTimeEdit()
        self.schedule_time.setDisplayFormat("HH:mm")
        self.schedule_time.setTime(QTime(20, 0))
        self.schedule_check = QCheckBox("Enable")
        bar.addWidget(self.schedule_time)
        bar.addWidget(self.schedule_check)

        bar.addWidget(_divider())

        hint = QLabel("\U0001f4a1 Drag rows to change Layer 2 priority.")
        hint.setStyleSheet("color:#c4b5fd;")
        bar.addWidget(hint)

        bar.addStretch()
        layout.addWidget(controls)

        self.rampage_table = DraggableTable(0, 10)
        self._setup_domain_table(self.rampage_table, draggable=True)
        self.rampage_table.row_moved.connect(self._on_rampage_rows_reordered)
        self.rampage_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.rampage_table.customContextMenuRequested.connect(
            lambda pos: self._context_menu(self.rampage_table, pos, "rampage")
        )
        layout.addWidget(self.rampage_table)

        self.rampage_stats_label = QLabel("\u26a1 Rampage queue: 0 | Armed: 0")
        self.rampage_stats_label.setStyleSheet("color:#475569;font-size:11px;padding:2px 4px;")
        layout.addWidget(self.rampage_stats_label)

        return page

    def _setup_domain_table(self, table, draggable=False):
        table.setHorizontalHeaderLabels([
            "\u2195",       # COL_DRAG
            "\u2713",       # COL_SNIPE  - selection
            "\U0001f3af",   # COL_AUTOBUY - per-domain auto-buy
            "Domain",       # COL_DOMAIN
            "Est. Drop Date",
            "Price",
            "WHOIS",
            "Status",
            "Next",
            "Actions",
        ])
        hh = table.horizontalHeader()
        hh.setSectionResizeMode(COL_DRAG,    QHeaderView.Fixed)
        table.setColumnWidth(COL_DRAG, 28)
        hh.setSectionResizeMode(COL_SNIPE,   QHeaderView.Fixed)
        table.setColumnWidth(COL_SNIPE, 32)
        hh.setSectionResizeMode(COL_AUTOBUY, QHeaderView.Fixed)
        table.setColumnWidth(COL_AUTOBUY, 32)
        hh.setSectionResizeMode(COL_DOMAIN,  QHeaderView.Stretch)
        hh.setSectionResizeMode(COL_DROP,    QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(COL_PRICE,   QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(COL_WHOIS,   QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(COL_STATUS,  QHeaderView.Stretch)
        hh.setSectionResizeMode(COL_NEXT,    QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(COL_ACT,     QHeaderView.ResizeToContents)

        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setSortingEnabled(False)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)

        if not draggable:
            table.setDragEnabled(False)
            table.setAcceptDrops(False)
            table.setDragDropMode(QAbstractItemView.NoDragDrop)

    def _build_whois_tab(self):
        w = QWidget()
        wl = QVBoxLayout(w)
        wl.setSpacing(8)

        wl.addWidget(_section_label("\U0001f50e Manual WHOIS Check"))

        r1 = QHBoxLayout()
        self.whois_input = QLineEdit(placeholderText="e.g. example.com")
        self.whois_input.returnPressed.connect(self._run_whois_manual)
        b = QPushButton("\U0001f50d Check Now")
        b.clicked.connect(self._run_whois_manual)
        r1.addWidget(self.whois_input)
        r1.addWidget(b)
        wl.addLayout(r1)

        self.whois_output = QTextEdit()
        self.whois_output.setReadOnly(True)
        self.whois_output.setMaximumHeight(160)
        self.whois_output.setStyleSheet(
            "background:#0f172a;color:#e2e8f0;font-family:Consolas,monospace;font-size:12px;padding:6px;"
        )
        wl.addWidget(self.whois_output)

        wl.addWidget(_section_label("\u23f1\ufe0f Auto WHOIS Monitor (Monitoring + Rampage)"))

        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Check every:"))

        self.whois_interval_cb = QComboBox()
        self.whois_interval_cb.addItems(["10 seconds", "30 seconds", "1 minute", "2 minutes", "5 minutes"])
        self.whois_interval_cb.setCurrentText("1 minute")
        r2.addWidget(self.whois_interval_cb)

        self.whois_auto_btn = QPushButton("\u25b6\ufe0f Start")
        self.whois_auto_btn.setCheckable(True)
        self.whois_auto_btn.clicked.connect(self._toggle_auto_whois)
        r2.addWidget(self.whois_auto_btn)

        self.whois_progress = QProgressBar()
        self.whois_progress.setMaximum(100)
        self.whois_progress.setValue(100)
        self.whois_progress.setFormat("Idle")
        self.whois_progress.setFixedHeight(18)
        self.whois_progress.setStyleSheet(
            "QProgressBar{background:#1e293b;border-radius:4px;color:#e2e8f0;font-size:11px;}"
            "QProgressBar::chunk{background:#7c3aed;border-radius:4px;}"
        )
        r2.addWidget(self.whois_progress, 1)

        wl.addLayout(r2)

        self.whois_auto_log = QTextEdit()
        self.whois_auto_log.setReadOnly(True)
        self.whois_auto_log.setStyleSheet(
            "background:#0f172a;color:#94a3b8;font-family:Consolas,monospace;font-size:11px;padding:6px;"
        )
        wl.addWidget(self.whois_auto_log)

        tip = QLabel("WHOIS runs in background threads, but all GUI updates return through Qt signals to keep the app responsive and stable.")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#475569;font-size:11px;padding:6px;border-top:1px solid #1e293b;")
        wl.addWidget(tip)

        return w

    def _build_ai_tab(self):
        w = QWidget()
        al = QVBoxLayout(w)
        al.setSpacing(6)

        intro = QLabel(
            "Paste domains below one per line, comma or space separated. Click Generate AI Prompt and a professional investment prompt is copied to the clipboard."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("padding:6px 4px;color:#cbd5e1;font-size:12px;")
        al.addWidget(intro)

        splitter = QSplitter(Qt.Vertical)

        in_box = QGroupBox("\U0001f9e0 Paste Domains Here")
        il = QVBoxLayout(in_box)
        self.ai_input = QTextEdit()
        self.ai_input.setPlaceholderText("coolbrand.com\nbesttech.net\nfinancehelp.org")
        self.ai_input.setStyleSheet("background:#1e293b;color:#f1f5f9;font-family:Consolas,monospace;font-size:12px;")
        il.addWidget(self.ai_input)

        opt = QHBoxLayout()
        opt.addStretch()

        b_gen = QPushButton("\u26a1 Generate AI Prompt + Copy")
        b_gen.setStyleSheet("background:#7c3aed;color:white;font-weight:bold;padding:8px 18px;border-radius:6px;")
        b_gen.clicked.connect(self.generate_ai_prompt)

        b_add = QPushButton("\u2795 Add All to Monitoring")
        b_add.clicked.connect(self._ai_add_all)

        opt.addWidget(b_gen)
        opt.addWidget(b_add)
        il.addLayout(opt)

        splitter.addWidget(in_box)

        prev_box = QGroupBox("\U0001f4cb Generated Prompt Preview")
        pl = QVBoxLayout(prev_box)

        self.ai_preview = QTextEdit()
        self.ai_preview.setReadOnly(True)
        self.ai_preview.setStyleSheet("background:#0f172a;color:#a5b4fc;font-family:Consolas,monospace;font-size:11px;")
        self.ai_preview.setPlaceholderText("Prompt appears here after clicking Generate...")
        pl.addWidget(self.ai_preview)

        b_copy = QPushButton("\U0001f4cc Copy Again")
        b_copy.clicked.connect(lambda: QApplication.clipboard().setText(self.ai_preview.toPlainText()))
        pl.addWidget(b_copy)

        splitter.addWidget(prev_box)
        al.addWidget(splitter)
        return w

    def _build_portfolio_tab(self):
        w = QWidget()
        pl = QVBoxLayout(w)
        pl.setSpacing(6)

        self.p_stats = QLabel("\U0001f4e6 Caught: 0 | Est. Total Spent: $0.00")
        self.p_stats.setStyleSheet(
            "background:#1e293b;color:#a5b4fc;font-size:13px;font-weight:bold;padding:10px 14px;border-radius:6px;"
        )
        pl.addWidget(self.p_stats)

        pl.addWidget(_section_label("\U0001f4e6 Caught Domains"))

        self.portfolio_table = QTableWidget(0, 5)
        self.portfolio_table.setHorizontalHeaderLabels(["Domain", "Caught At", "Price Paid", "Status", "Notes"])
        ph = self.portfolio_table.horizontalHeader()
        ph.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3):
            ph.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        ph.setSectionResizeMode(4, QHeaderView.Stretch)
        self.portfolio_table.setAlternatingRowColors(True)
        self.portfolio_table.setEditTriggers(QTableWidget.DoubleClicked)
        pl.addWidget(self.portfolio_table)

        r = QHBoxLayout()
        b1 = QPushButton("\U0001f4e4 Export Portfolio CSV")
        b1.clicked.connect(self.export_portfolio)
        b2 = QPushButton("\U0001f5d1 Clear Portfolio")
        b2.clicked.connect(self._clear_portfolio)
        r.addWidget(b1)
        r.addWidget(b2)
        r.addStretch()
        pl.addLayout(r)

        tip = QLabel("Double-click the Notes column to add your own text per domain.")
        tip.setStyleSheet("color:#475569;font-size:11px;padding:4px;")
        pl.addWidget(tip)

        return w

    def _build_info_tab(self):
        w = QWidget()
        il = QVBoxLayout(w)

        il.addWidget(_section_label("\U0001f552 TLD Drop Windows (Freiburg local time)"))

        dt = QTableWidget(len(DROP_TIMES_TABLE), 4)
        dt.setHorizontalHeaderLabels(["TLD", "UTC", "Local", "Notes"])
        dt.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        dt.setEditTriggers(QTableWidget.NoEditTriggers)
        dt.verticalHeader().setVisible(False)
        dt.setMaximumHeight(170)

        for i, row in enumerate(DROP_TIMES_TABLE):
            for j, v in enumerate(row):
                dt.setItem(i, j, QTableWidgetItem(v))
        il.addWidget(dt)

        il.addWidget(_section_label("\U0001f4b5 Standard Registration Prices"))
        pl = QLabel(" " + " | ".join(f".{t}: ${p:.2f}" for t, p in sorted(TLD_PRICES.items(), key=lambda x: x[1])))
        pl.setWordWrap(True)
        pl.setStyleSheet("background:#1e293b;color:#94a3b8;font-family:Consolas;font-size:11px;padding:8px;border-radius:6px;")
        il.addWidget(pl)

        il.addWidget(_section_label("\U0001f9ed Workflow"))
        g = QTextEdit()
        g.setReadOnly(True)
        g.setStyleSheet("background:#1e293b;color:#cbd5e1;font-size:12px;padding:8px;")
        g.setHtml("""
            <ol>
                <li>Filter candidates in <b>Monitoring</b>.</li>
                <li>Run WHOIS and premium checks there.</li>
                <li>Push only the best domains into <b>Rampage Queue</b>.</li>
                <li>Use drag order in Rampage to set Layer 2 priority.</li>
                <li>Schedule or start Rampage when the drop window opens.</li>
            </ol>
        """)
        il.addWidget(g)

        return w

    def _build_settings_tab(self):
        w = QWidget()
        sl = QVBoxLayout(w)
        sl.setSpacing(8)

        sl.addWidget(_section_label("\u2699\ufe0f Application Settings"))

        formbox = QGroupBox("General")
        formbox.setStyleSheet(
            "QGroupBox{color:#94a3b8;font-size:11px;border:1px solid #1e293b;border-radius:6px;margin-top:4px;padding:8px;}"
        )
        fl = QFormLayout(formbox)
        fl.setSpacing(10)

        self.s_ontop = QCheckBox("Always on top")
        self.s_ontop.setChecked(self.settings.get("always_on_top", False))
        self.s_ontop.toggled.connect(self._toggle_on_top)
        fl.addRow("Window", self.s_ontop)

        self.s_tray = QCheckBox("Minimize to tray instead of closing")
        self.s_tray.setChecked(self.settings.get("minimize_to_tray", True))
        self.s_tray.toggled.connect(lambda v: self._save_setting("minimize_to_tray", v))
        fl.addRow("Close button", self.s_tray)

        self.s_sound = QCheckBox("Sound alerts")
        self.s_sound.setChecked(self.settings.get("sound", True))
        self.s_sound.toggled.connect(lambda v: self._save_setting("sound", v))
        fl.addRow("Notifications", self.s_sound)

        self.s_maxprem = QSpinBox()
        self.s_maxprem.setRange(0, 100000)
        self.s_maxprem.setValue(self.settings.get("max_premium", 500))
        self.s_maxprem.setSuffix(" USD (0 = always ask)")
        self.s_maxprem.valueChanged.connect(lambda v: self._save_setting("max_premium", v))
        fl.addRow("Auto-skip premium above", self.s_maxprem)

        sl.addWidget(formbox)

        resetbox = QGroupBox("Data reset")
        resetbox.setStyleSheet(
            "QGroupBox{color:#94a3b8;font-size:11px;border:1px solid #1e293b;border-radius:6px;margin-top:4px;padding:8px;}"
        )
        rl = QHBoxLayout(resetbox)
        b1 = QPushButton("Clear Monitoring")
        b1.clicked.connect(self.clear_watchlist)
        b2 = QPushButton("Clear Activity Log")
        b2.clicked.connect(self.log.clear)
        rl.addWidget(b1)
        rl.addWidget(b2)
        rl.addStretch()
        sl.addWidget(resetbox)

        sl.addStretch()
        return w
