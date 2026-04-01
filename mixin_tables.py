# mixin_tables.py
# Table helpers, row factories, context menu, and stats-bar methods
# for DropCatcher.
import webbrowser
import re

from PyQt5.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QPushButton,
    QTableWidgetItem, QMenu, QLabel,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

from constants import (
    COL_DRAG, COL_SNIPE, COL_AUTOBUY, COL_DOMAIN,
    COL_DROP, COL_PRICE, COL_WHOIS, COL_STATUS, COL_NEXT, COL_ACT,
)
from utils import normalize_domain, get_tld_price, get_drop_window
from persistence import save_watchlist
from sniper import update_domain_row


class UiTablesMixin:
    """Mixin: table helpers, row factories, context menu, stats bar."""

    # ------------------------------------------------------------------ #
    #  Per-domain Auto-Buy helpers                                         #
    # ------------------------------------------------------------------ #
    def _autobuy_item(self, checked=False):
        """Create a checkable QTableWidgetItem for the COL_AUTOBUY column."""
        item = QTableWidgetItem()
        item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        item.setTextAlignment(Qt.AlignCenter)
        item.setToolTip(
            "Per-domain Auto-Buy toggle (\U0001f3af).\n"
            "When CHECKED here AND the global \u26a0\ufe0f Enable Auto-Buy is ON,\n"
            "this domain will be purchased automatically when available.\n"
            "Leave unchecked to monitor without buying."
        )
        return item

    def domain_autobuy_enabled(self, domain):
        """Return True only when global AND per-row Auto-Buy are both ON."""
        global_on = getattr(self, "auto_buy_chk", None) and self.auto_buy_chk.isChecked()
        if not global_on:
            return False
        row = self.monitor_rows.get(domain)
        if row is None:
            return False
        item = self.monitor_table.item(row, COL_AUTOBUY)
        return bool(item and item.checkState() == Qt.Checked)

    # ------------------------------------------------------------------ #
    #  Row helpers                                                         #
    # ------------------------------------------------------------------ #
    def _row_button(self, text, tooltip, slot, width=28):
        b = QPushButton(text)
        b.setFixedWidth(width)
        b.setToolTip(tooltip)
        b.clicked.connect(slot)
        return b

    def _make_action_cell(self, domain, mode):
        cell = QWidget()
        cl = QHBoxLayout(cell)
        cl.setContentsMargins(2, 1, 2, 1)
        cl.setSpacing(2)

        if mode == "monitor":
            buttons = [
                self._row_button("W",  "Run WHOIS",                lambda _, d=domain: self.run_whois_row(d)),
                self._row_button("$",  "Check premium",             lambda _, d=domain: self.run_premium_check(d)),
                self._row_button("\u25b6",  "Start Monitoring",    lambda _, d=domain: self.start_monitor_for_domain(d)),
                self._row_button("\u23f9", "Stop Monitoring",       lambda _, d=domain: self.stop_domain(d, "monitor")),
                self._row_button("\u26a1", "Add to Rampage queue",  lambda _, d=domain: self.queue_from_monitor(d)),
                self._row_button("\u2716", "Remove from Monitoring",lambda _, d=domain: self.remove_monitor(d)),
            ]
        else:
            buttons = [
                self._row_button("W",  "Run WHOIS",                    lambda _, d=domain: self.run_whois_row(d)),
                self._row_button("\u25b6",  "Start Rampage",           lambda _, d=domain: self.launch_rampage(d)),
                self._row_button("\u23f9", "Stop Rampage",              lambda _, d=domain: self.stop_domain(d, "rampage")),
                self._row_button("\u2716", "Remove from Rampage queue", lambda _, d=domain: self.remove_rampage(d)),
            ]

        for b in buttons:
            cl.addWidget(b)
        return cell

    def _new_drag_item(self, draggable=False, text=""):
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignCenter)
        item.setForeground(QColor("#475569"))
        flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        if draggable:
            flags |= Qt.ItemIsDragEnabled
        item.setFlags(flags)
        return item

    def _checked_item(self, checked=True):
        item = QTableWidgetItem()
        item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        item.setTextAlignment(Qt.AlignCenter)
        return item

    def _center_item(self, text, color=None):
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignCenter)
        if color:
            item.setForeground(QColor(color))
        return item

    # ------------------------------------------------------------------ #
    #  Row factories                                                       #
    # ------------------------------------------------------------------ #
    def _add_monitor_row(self, domain):
        domain = normalize_domain(domain)
        if not domain or domain in self.monitor_rows:
            return False

        row = self.monitor_table.rowCount()
        self.monitor_table.insertRow(row)
        self.monitor_table.setItem(row, COL_DRAG,    self._new_drag_item(False))
        self.monitor_table.setItem(row, COL_SNIPE,   self._checked_item(True))
        self.monitor_table.setItem(row, COL_AUTOBUY, self._autobuy_item(False))
        self.monitor_table.setItem(row, COL_DOMAIN,  QTableWidgetItem(domain))
        self.monitor_table.setItem(row, COL_DROP,    self._center_item("Run WHOIS", "#64748b"))
        self.monitor_table.setItem(row, COL_PRICE,   self._center_item(get_tld_price(domain), "#4ade80"))
        self.monitor_table.setItem(row, COL_WHOIS,   self._center_item("-"))
        self.monitor_table.setItem(row, COL_STATUS,  QTableWidgetItem("Idle"))
        self.monitor_table.setItem(row, COL_NEXT,    self._center_item(get_drop_window(domain), "#64748b"))
        self.monitor_table.setCellWidget(row, COL_ACT, self._make_action_cell(domain, "monitor"))
        self.monitor_rows[domain] = row

        with self.monitor_scheduler_lock:
            self._ensure_monitor_runtime_unlocked(domain)

        self.refresh_stats()
        return True

    def _add_rampage_row(self, domain):
        domain = normalize_domain(domain)
        if not domain or domain in self.rampage_rows:
            return False

        row = self.rampage_table.rowCount()
        self.rampage_table.insertRow(row)
        self.rampage_table.setItem(row, COL_DRAG,    self._new_drag_item(True))
        self.rampage_table.setItem(row, COL_SNIPE,   self._checked_item(True))
        self.rampage_table.setItem(row, COL_AUTOBUY, self._center_item("-", "#334155"))  # N/A for rampage
        self.rampage_table.setItem(row, COL_DOMAIN,  QTableWidgetItem(domain))
        self.rampage_table.setItem(row, COL_DROP,    self._center_item("Run WHOIS", "#64748b"))
        self.rampage_table.setItem(row, COL_PRICE,   self._center_item(get_tld_price(domain), "#4ade80"))
        self.rampage_table.setItem(row, COL_WHOIS,   self._center_item("-"))
        self.rampage_table.setItem(row, COL_STATUS,  QTableWidgetItem("Queued"))
        self.rampage_table.setItem(row, COL_NEXT,    self._center_item(get_drop_window(domain), "#64748b"))
        self.rampage_table.setCellWidget(row, COL_ACT, self._make_action_cell(domain, "rampage"))
        self.rampage_rows[domain] = row
        self.refresh_stats()
        return True

    def _remove_from_table(self, table, rowmap, nextmap, domain, mode):
        row = rowmap.get(domain)
        if row is None:
            return

        self.stop_domain(domain, mode)
        table.removeRow(row)
        nextmap.pop(domain, None)
        self._rebuild_rows(table, rowmap, mode)

        if mode == "monitor":
            with self.monitor_scheduler_lock:
                self.monitor_runtime.pop(domain, None)

        self.append_log(f"Removed {domain} from {'Rampage queue' if mode == 'rampage' else 'Monitoring'}.")

    def _rebuild_rows(self, table, rowmap, mode):
        rowmap.clear()
        for r in range(table.rowCount()):
            item = table.item(r, COL_DOMAIN)
            if item:
                domain = item.text()
                rowmap[domain] = r
                table.setCellWidget(r, COL_ACT, self._make_action_cell(domain, mode))

    def _on_rampage_rows_reordered(self):
        self._rebuild_rows(self.rampage_table, self.rampage_rows, "rampage")
        for d, r in self.rampage_rows.items():
            update_domain_row(d, r)
        self._save_rampage_queue()
        self.append_log("Rampage row order updated.")

    # ------------------------------------------------------------------ #
    #  Check All / Uncheck All  +  Arm All / Disarm All                   #
    # ------------------------------------------------------------------ #
    def check_all_monitor(self):
        for row in range(self.monitor_table.rowCount()):
            item = self.monitor_table.item(row, COL_SNIPE)
            if item:
                item.setCheckState(Qt.Checked)

    def uncheck_all_monitor(self):
        for row in range(self.monitor_table.rowCount()):
            item = self.monitor_table.item(row, COL_SNIPE)
            if item:
                item.setCheckState(Qt.Unchecked)

    def check_all_rampage(self):
        for row in range(self.rampage_table.rowCount()):
            item = self.rampage_table.item(row, COL_SNIPE)
            if item:
                item.setCheckState(Qt.Checked)

    def uncheck_all_rampage(self):
        for row in range(self.rampage_table.rowCount()):
            item = self.rampage_table.item(row, COL_SNIPE)
            if item:
                item.setCheckState(Qt.Unchecked)

    def _arm_all_autobuy(self):
        count = 0
        for row in range(self.monitor_table.rowCount()):
            item = self.monitor_table.item(row, COL_AUTOBUY)
            if item and item.checkState() != Qt.Checked:
                item.setCheckState(Qt.Checked)
                count += 1
        self.append_log(f"[AUTO-BUY] Armed {count} domain(s).")
        self.refresh_stats()

    def _disarm_all_autobuy(self):
        count = 0
        for row in range(self.monitor_table.rowCount()):
            item = self.monitor_table.item(row, COL_AUTOBUY)
            if item and item.checkState() == Qt.Checked:
                item.setCheckState(Qt.Unchecked)
                count += 1
        self.append_log(f"[AUTO-BUY] Disarmed {count} domain(s).")
        self.refresh_stats()

    # ------------------------------------------------------------------ #
    #  Filters                                                            #
    # ------------------------------------------------------------------ #
    def _filter_monitor_table(self, text):
        self._filter_table(self.monitor_table, COL_DOMAIN, text)

    def _filter_rampage_table(self, text):
        self._filter_table(self.rampage_table, COL_DOMAIN, text)

    def _filter_table(self, table, domain_col, text):
        text = (text or "").lower().strip()
        for row in range(table.rowCount()):
            item = table.item(row, domain_col)
            table.setRowHidden(row, bool(text and item and text not in item.text().lower()))

    def _checked_in_table(self, table, rowmap, domain):
        row = rowmap.get(domain)
        if row is None:
            return False
        item = table.item(row, COL_SNIPE)
        return bool(item and item.checkState() == Qt.Checked)

    def _set_item_if_present(self, table, rowmap, domain, col, item):
        row = rowmap.get(domain)
        if row is None:
            return
        table.setItem(row, col, item)

    def _set_status_in_tables(self, domain, text, color="#94a3b8"):
        row = self.monitor_rows.get(domain)
        if row is not None:
            item = QTableWidgetItem(text)
            item.setForeground(QColor(color))
            self.monitor_table.setItem(row, COL_STATUS, item)

        row = self.rampage_rows.get(domain)
        if row is not None:
            item = QTableWidgetItem(text)
            item.setForeground(QColor(color))
            self.rampage_table.setItem(row, COL_STATUS, item)

    # ------------------------------------------------------------------ #
    #  Context menu                                                        #
    # ------------------------------------------------------------------ #
    def _context_menu(self, table, pos, mode):
        row = table.rowAt(pos.y())
        if row < 0:
            return

        item = table.item(row, COL_DOMAIN)
        if not item:
            return

        domain = item.text().strip()
        if not domain:
            return

        menu = QMenu(self)

        menu.addAction("\U0001f50e Check WHOIS",   lambda d=domain: self.run_whois_row(d))
        menu.addAction("\U0001f48e Check Premium", lambda d=domain: self.run_premium_check(d))

        if mode == "monitor":
            menu.addSeparator()
            menu.addAction("\U0001f3af Start Monitoring", lambda d=domain: self.start_monitor_for_domain(d))
            menu.addAction("\u23f9 Stop Monitoring",      lambda d=domain: self.stop_domain(d, "monitor"))
            menu.addAction("\u26a1 Add to Rampage Queue", lambda d=domain: self.queue_from_monitor(d))
            menu.addSeparator()
            ab_item = self.monitor_table.item(row, COL_AUTOBUY)
            is_armed = ab_item and ab_item.checkState() == Qt.Checked
            label = "\U0001f3af Disarm Auto-Buy for this domain" if is_armed else "\U0001f3af Arm Auto-Buy for this domain"
            menu.addAction(label, lambda d=domain, r=row: self._toggle_autobuy_row(r))
        else:
            menu.addSeparator()
            menu.addAction("\u25b6\ufe0f Start Rampage", lambda d=domain: self.launch_rampage(d))
            menu.addAction("\u23f9 Stop Rampage",        lambda d=domain: self.stop_domain(d, "rampage"))

        menu.addSeparator()
        menu.addAction("\U0001f4cb Copy Domain Name", lambda d=domain: QApplication.clipboard().setText(d))

        mkts = menu.addMenu("\U0001f310 Marketplaces")
        mkts.addAction("ExpiredDomains.net", lambda d=domain: webbrowser.open(f"https://member.expireddomains.net/domain/{d}"))
        mkts.addAction("Sedo",               lambda d=domain: webbrowser.open(f"https://sedo.com/search/searchresult.php4?keyword={d}&language=e"))
        mkts.addAction("Afternic",           lambda d=domain: webbrowser.open(f"https://www.afternic.com/forsale/{d}"))
        mkts.addAction("Dan.com",            lambda d=domain: webbrowser.open(f"https://dan.com/domain/{d}"))
        mkts.addAction("SnapNames",          lambda d=domain: webbrowser.open(f"https://www.snapnames.com/domain/{d}.action"))
        mkts.addAction("Flippa",             lambda d=domain: webbrowser.open(f"https://flippa.com/search?filter[keyword]={d}"))

        appr = menu.addMenu("\U0001f4b0 Appraisal Tools")
        appr.addAction("HumbleWorth AI",    lambda d=domain: webbrowser.open(f"https://humbleworth.com/valuation/single?domain={d}"))
        appr.addAction("Hazlo.ai",          lambda d=domain: webbrowser.open(f"https://hazlo.ai/appraisal?domain={d}"))
        appr.addAction("Dynadot Appraisal", lambda d=domain: webbrowser.open(f"https://www.dynadot.com/domain/appraisal?domain={d}"))
        appr.addAction("Atom.com",          lambda d=domain: webbrowser.open(f"https://www.atom.com/domain-appraisal?domain={d}"))
        appr.addAction("Estibot",           lambda d=domain: webbrowser.open(f"https://www.estibot.com/appraise.php?a={d}"))

        research = menu.addMenu("\U0001f9ea Research")
        research.addAction("DomainTools WHOIS", lambda d=domain: webbrowser.open(f"https://whois.domaintools.com/{d}"))
        research.addAction("Wayback Machine",   lambda d=domain: webbrowser.open(f"https://web.archive.org/web/*/{d}"))
        research.addAction("Moz",               lambda d=domain: webbrowser.open(f"https://moz.com/domain-analysis?site={d}"))

        menu.addSeparator()
        if mode == "monitor":
            menu.addAction("\U0001f5d1 Remove from Monitoring",    lambda d=domain: self.remove_monitor(d))
        else:
            menu.addAction("\U0001f5d1 Remove from Rampage Queue", lambda d=domain: self.remove_rampage(d))

        menu.exec_(table.viewport().mapToGlobal(pos))

    def _toggle_autobuy_row(self, row):
        item = self.monitor_table.item(row, COL_AUTOBUY)
        if item:
            new_state = Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked
            item.setCheckState(new_state)
            domain_item = self.monitor_table.item(row, COL_DOMAIN)
            domain = domain_item.text() if domain_item else "?"
            state_str = "armed" if new_state == Qt.Checked else "disarmed"
            self.append_log(f"[AUTO-BUY] {domain} {state_str}.")
            self.refresh_stats()

    # ------------------------------------------------------------------ #
    #  Stats bar                                                          #
    # ------------------------------------------------------------------ #
    def refresh_stats(self):
        active_monitor = self._count_active_monitor_domains()

        armed_rampage = 0
        for d in self.rampage_rows.keys():
            ev = self._stop_event_for(d, "rampage")
            if ev and not ev.is_set():
                armed_rampage += 1

        autobuy_armed = 0
        for row in range(self.monitor_table.rowCount()):
            item = self.monitor_table.item(row, COL_AUTOBUY)
            if item and item.checkState() == Qt.Checked:
                autobuy_armed += 1
        ab_suffix = f" | \U0001f3af Auto-Buy armed: {autobuy_armed}" if autobuy_armed else ""

        self.monitor_stats_label.setText(
            f"\U0001f4e1 Monitoring domains: {len(self.monitor_rows)} | Active: {active_monitor}{ab_suffix}"
        )
        self.rampage_stats_label.setText(f"\u26a1 Rampage queue: {len(self.rampage_rows)} | Armed: {armed_rampage}")

        total_spent = 0.0
        for row in range(self.portfolio_table.rowCount()):
            item = self.portfolio_table.item(row, 2)
            if not item:
                continue
            txt = str(item.text()).strip()
            m = re.search(r"[0-9]+(?:\.[0-9]+)?", txt.replace(",", ""))
            if m:
                try:
                    total_spent += float(m.group(0))
                except Exception:
                    pass

        self.p_stats.setText(f"\U0001f4e6 Caught: {self.portfolio_table.rowCount()} | Est. Total Spent: ${total_spent:.2f}")
        self._update_monitor_delay_label()
