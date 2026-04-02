import time
# mixin_actions.py
# All domain add / remove / start / stop / queue action methods
# for DropCatcher.
import re
import threading

from PyQt5.QtWidgets import QFileDialog

from sniper import snipe_domain
from utils import normalize_domain
from persistence import save_watchlist


class ActionsMixin:
    """Mixin: domain add, remove, start, stop, and queue actions."""

    def add_domain(self):
        d = normalize_domain(self.input.text())
        if d:
            self._add_monitor_row(d)
            save_watchlist(self.monitor_rows.keys())
            self.input.clear()
            self.refresh_stats()

    def import_txt(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open domain list", "", "Text Files (*.txt)")
        if not path:
            return
        with open(path, "r", encoding="utf-8") as f:
            lines = [normalize_domain(l) for l in f]
        self._bulk_add_monitor([d for d in lines if d])

    def _ai_add_all(self):
        tokens = re.split(r"[\s,;]+", self.ai_input.toPlainText())
        self._bulk_add_monitor([normalize_domain(t) for t in tokens if normalize_domain(t)])

    def _bulk_add_monitor(self, domains):
        added = 0
        for d in domains:
            if self._add_monitor_row(d):
                added += 1
        save_watchlist(self.monitor_rows.keys())
        self.append_log(f"Added {added} domains to Monitoring.")
        self.refresh_stats()

    def add_rampage_domain(self):
        d = normalize_domain(self.rampage_input.text())
        if d:
            self._add_rampage_row(d)
            self._save_rampage_queue()
            self.rampage_input.clear()
            self.refresh_stats()

    def add_checked_to_rampage(self):
        added = 0
        for domain in list(self.monitor_rows.keys()):
            if self._checked_in_table(self.monitor_table, self.monitor_rows, domain):
                if self._add_rampage_row(domain):
                    added += 1
        self._save_rampage_queue()
        self.append_log(f"Added {added} checked Monitoring domains to Rampage queue.")
        self.refresh_stats()

    def clear_rampage_queue(self):
        domains = list(self.rampage_rows.keys())
        self.rampage_table.setRowCount(0)
        self.rampage_rows.clear()
        self.rampage_next_ts.clear()
        for domain in domains:
            self.stop_domain(domain, "rampage")
        self._save_rampage_queue()
        self.refresh_stats()
        self.append_log("Rampage queue cleared.")

    def bulk_whois(self):
        seen = set()
        for d in list(self.monitor_rows.keys()) + list(self.rampage_rows.keys()):
            if d not in seen:
                seen.add(d)
                self.run_whois_row(d)

    def start_monitor_for_domain(self, domain):
        domain = normalize_domain(domain)
        if not domain or domain not in self.monitor_rows:
            return

        now = time.time()
        stop_after_ts = None
        if self.auto_stop.value() > 0:
            stop_after_ts = now + self.auto_stop.value() * 3600

        with self.monitor_scheduler_lock:
            st = self._ensure_monitor_runtime_unlocked(domain)
            st["active"] = True
            st["inflight"] = False
            st["stop_after_ts"] = stop_after_ts
            st["next_allowed_at"] = min(st.get("next_allowed_at", now) or now, now)

        self._set_status_in_tables(domain, "Queued for monitoring...", "#93c5fd")
        self.monitor_next_ts[domain] = now
        self.append_log(f"{domain} monitoring queued.")
        self.refresh_stats()
        self._wake_monitor_scheduler()

    def start_checked_monitoring(self):
        checked = [d for d in list(self.monitor_rows.keys()) if self._checked_in_table(self.monitor_table, self.monitor_rows, d)]
        if not checked:
            self.append_log("No checked Monitoring domains to start.")
            return
        for d in checked:
            self.start_monitor_for_domain(d)
        self.append_log(f"Queued monitoring for {len(checked)} checked domains.")

    def stop_checked_monitoring(self):
        checked = [d for d in list(self.monitor_rows.keys()) if self._checked_in_table(self.monitor_table, self.monitor_rows, d)]
        if not checked:
            self.append_log("No checked Monitoring domains to stop.")
            return
        for d in checked:
            self.stop_domain(d, "monitor")
        self.append_log(f"Stopped monitoring for {len(checked)} checked domains.")

    def stop_all_monitoring(self):
        domains = list(self.monitor_rows.keys())
        if not domains:
            self.append_log("Monitoring list is empty.")
            return
        for d in domains:
            self.stop_domain(d, "monitor")
        self.append_log("Stopped monitoring for all Monitoring domains.")

    def start_rampage_all(self):
        if not self.rampage_rows:
            self.append_log("Rampage queue is empty.")
            return
        started = 0
        for d in list(self.rampage_rows.keys()):
            if self._checked_in_table(self.rampage_table, self.rampage_rows, d):
                self.launch_rampage(d)
                started += 1
        self.append_log(f"Started Rampage for {started} checked domains.")

    def stop_checked_rampage(self):
        checked = [d for d in list(self.rampage_rows.keys()) if self._checked_in_table(self.rampage_table, self.rampage_rows, d)]
        if not checked:
            self.append_log("No checked Rampage domains to stop.")
            return
        for d in checked:
            self.stop_domain(d, "rampage")
        self.append_log(f"Stopped Rampage for {len(checked)} checked domains.")

    def stop_all_rampage(self):
        domains = list(self.rampage_rows.keys())
        if not domains:
            self.append_log("Rampage queue is empty.")
            return
        for d in domains:
            self.stop_domain(d, "rampage")
        self.append_log("Stopped Rampage for all queued domains.")

    def _launch(self, domain, mode, rampage=False):
        interval = self._get_poll_interval()
        rowmap = self.rampage_rows if mode == "rampage" else self.monitor_rows
        rowindex = rowmap.get(domain, 999)

        old_ev = self._stop_event_for(domain, mode)
        if old_ev:
            old_ev.set()

        stop_event = threading.Event()
        self._set_stop_event_for(domain, mode, stop_event)

        self._update_status(domain, "Starting Rampage..." if rampage else "Starting monitor...")
        if rampage:
            self.append_log(f"{domain} entered Layer 2 queue.")
        else:
            self.append_log(f"{domain} monitoring started.")

        threading.Thread(
            target=snipe_domain,
            kwargs=dict(
                domain=domain,
                onstatus=lambda d, s, m=mode: self.signals.status_update.emit(
                    d, f"{s}" if m == "rampage" or not str(s).startswith("Rampage queued") else s
                ),
                onsuccess=lambda d, r: self.signals.success.emit(d, r),
                onfailure=lambda d, e: self.signals.failure.emit(d, e),
                onpremium=lambda d, p, c: self.signals.premium_detect.emit(d, float(p or 0), c),
                onnextcheck=lambda d, ts, m=mode: self.signals.next_check.emit(d, ts, m),
                pollinterval=interval,
                rampage=True,
                rowindex=rowindex,
                stopevent=stop_event,
            ),
            daemon=True,
        ).start()

    def launch_monitor(self, domain):
        self.start_monitor_for_domain(domain)

    def launch_rampage(self, domain):
        self._launch(domain, "rampage", rampage=True)

    def stop_domain(self, domain, mode=None, silent=False):
        """
        Stop monitoring/rampage for *domain*.
        silent=True suppresses the per-mode log line (used when the caller
        will emit its own 'Removed' message immediately after).
        """
        modes = [mode] if mode else ["monitor", "rampage"]

        for m in modes:
            if m == "monitor":
                with self.monitor_scheduler_lock:
                    st = self.monitor_runtime.get(domain)
                    if st:
                        st["active"] = False
                        st["inflight"] = False
                        st["stop_after_ts"] = None
                self.monitor_next_ts.pop(domain, None)
                self._set_status_in_tables(domain, "Stopped", "#94a3b8")
                if not silent:
                    self.append_log(f"Stopped monitor for {domain}.")
                self._wake_monitor_scheduler()
                continue

            ev = self._stop_event_for(domain, m)
            if ev and not ev.is_set():
                ev.set()
            self._pop_stop_event_for(domain, m)

            if m == "rampage":
                self.rampage_next_ts.pop(domain, None)

            self._set_status_in_tables(domain, "Stopped", "#94a3b8")
            if not silent:
                self.append_log(f"Stopped {m} for {domain}.")

        self.refresh_stats()

    def queue_from_monitor(self, domain):
        if self._add_rampage_row(domain):
            self._save_rampage_queue()
            self.append_log(f"{domain} added to Rampage queue.")
            self.sniper_tabs.setCurrentIndex(1)
        self.refresh_stats()

    def remove_monitor(self, domain):
        self._remove_from_table(self.monitor_table, self.monitor_rows, self.monitor_next_ts, domain, "monitor")
        save_watchlist(self.monitor_rows.keys())
        self.refresh_stats()

    def remove_rampage(self, domain):
        self._remove_from_table(self.rampage_table, self.rampage_rows, self.rampage_next_ts, domain, "rampage")
        self._save_rampage_queue()
        self.refresh_stats()

    # ------------------------------------------------------------------ #
    #  Bulk action dispatchers ("With checked..." toolbar)                #
    # ------------------------------------------------------------------ #

    def _apply_monitor_bulk_action(self):
        action = self.monitor_bulk_action.currentText()
        if action.startswith("\u2014"):
            return

        checked = [
            d for d in list(self.monitor_rows.keys())
            if self._checked_in_table(self.monitor_table, self.monitor_rows, d)
        ]
        if not checked:
            self.append_log("No checked domains — nothing to apply.")
            return

        if action == "Remove":
            for d in checked:
                self.remove_monitor(d)
            self.append_log(f"Removed {len(checked)} domain(s) from Monitoring.")
        elif action == "Start monitoring":
            for d in checked:
                self.start_monitor_for_domain(d)
            self.append_log(f"Started monitoring for {len(checked)} domain(s).")
        elif action == "Stop monitoring":
            for d in checked:
                self.stop_domain(d, "monitor")
            self.append_log(f"Stopped monitoring for {len(checked)} domain(s).")
        elif action == "Move to Rampage":
            added = sum(1 for d in checked if self._add_rampage_row(d))
            self._save_rampage_queue()
            self.append_log(f"Moved {added} domain(s) to Rampage queue.")
            self.sniper_tabs.setCurrentIndex(1)
        elif action == "Run WHOIS":
            for d in checked:
                self.run_whois_row(d)
            self.append_log(f"WHOIS queued for {len(checked)} domain(s).")
        elif action == "Arm Auto-Buy":
            from constants import COL_AUTOBUY
            from PyQt5.QtCore import Qt
            count = 0
            for d in checked:
                row = self.monitor_rows.get(d)
                if row is not None:
                    item = self.monitor_table.item(row, COL_AUTOBUY)
                    if item and item.checkState() != Qt.Checked:
                        item.setCheckState(Qt.Checked)
                        count += 1
            self.append_log(f"[AUTO-BUY] Armed {count} checked domain(s).")
        elif action == "Disarm Auto-Buy":
            from constants import COL_AUTOBUY
            from PyQt5.QtCore import Qt
            count = 0
            for d in checked:
                row = self.monitor_rows.get(d)
                if row is not None:
                    item = self.monitor_table.item(row, COL_AUTOBUY)
                    if item and item.checkState() == Qt.Checked:
                        item.setCheckState(Qt.Unchecked)
                        count += 1
            self.append_log(f"[AUTO-BUY] Disarmed {count} checked domain(s).")

        self.monitor_bulk_action.setCurrentIndex(0)
        self.refresh_stats()

    def _apply_rampage_bulk_action(self):
        action = self.rampage_bulk_action.currentText()
        if action.startswith("\u2014"):
            return

        checked = [
            d for d in list(self.rampage_rows.keys())
            if self._checked_in_table(self.rampage_table, self.rampage_rows, d)
        ]
        if not checked:
            self.append_log("No checked Rampage domains — nothing to apply.")
            return

        if action == "Remove":
            for d in checked:
                self.remove_rampage(d)
            self.append_log(f"Removed {len(checked)} domain(s) from Rampage queue.")
        elif action == "Start Rampage":
            for d in checked:
                self.launch_rampage(d)
            self.append_log(f"Started Rampage for {len(checked)} domain(s).")
        elif action == "Stop Rampage":
            for d in checked:
                self.stop_domain(d, "rampage")
            self.append_log(f"Stopped Rampage for {len(checked)} domain(s).")
        elif action == "Run WHOIS":
            for d in checked:
                self.run_whois_row(d)
            self.append_log(f"WHOIS queued for {len(checked)} Rampage domain(s).")

        self.rampage_bulk_action.setCurrentIndex(0)
        self.refresh_stats()
