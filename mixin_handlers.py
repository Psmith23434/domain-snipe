import webbrowser
import re
import time
# mixin_handlers.py
# Signal callbacks, settings, misc UI state, and export methods
# for DropCatcher.
import csv
import threading
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QMessageBox, QFileDialog, QTableWidgetItem,
    QStyle,
)
from PyQt5.QtCore import Qt, QTime
from PyQt5.QtGui import QColor

from sniper import set_priority_enabled, POLL_MODES
from api import check_domain
from constants import (
    COL_DROP, COL_PRICE, COL_STATUS, COL_WHOIS, COL_NEXT,
    MONITOR_MAX_USER_RPS_DELAY, MONITOR_MIN_PER_DOMAIN_INTERVAL,
)
from utils import (
    normalize_domain,
    get_tld_price,
    estimate_drop_date,
    _extract_expiry_from_raw_whois,
    _first_datetime,
    _norm_status,
)
from persistence import load_settings, save_settings, save_watchlist


class HandlersMixin:
    """Mixin: signal callbacks, settings, misc UI state, and export methods."""

    def closeEvent(self, e):
        if self.settings.get("minimize_to_tray", True):
            e.ignore()
            self.hide()
            self.tray.showMessage(
                "Still running",
                "Drop Catcher is still monitoring in the system tray.",
                QSystemTrayIcon.Information,
                3000,
            )
        else:
            self.monitor_scheduler_stop.set()
            self.monitor_scheduler_wake.set()
            self.whois_worker_stop.set()
            self.whois_worker_wake.set()
            e.accept()

    # ------------------------------------------------------------------
    #  WHOIS result display  (called from signals thread → GUI thread)
    # ------------------------------------------------------------------

    def _show_whois_result(self, domain, raw_whois):
        """Parse a raw WHOIS string and update the monitoring/rampage row."""
        status_norm = _norm_status(raw_whois)
        drop_est    = estimate_drop_date(raw_whois) or ""

        # ── Determine display label + colour ──────────────────────────
        if "pendingdelete" in status_norm:
            short, color = "pendingDelete", QColor("#f87171")

        elif any(k in status_norm for k in ("redemptionperiod", "pendingrenewaldeletion", "redemption")):
            short, color = "Redemption", QColor("#f59e0b")

        elif "active" in status_norm or status_norm == "ok":
            # Check if it's a recently re-registered domain (~1-2 yr expiry = just bought after drop)
            if drop_est and drop_est.startswith("- (active, exp "):
                m = re.search(r"exp (\d{2})\.(\d{2})\.(\d{4})", drop_est)
                if m:
                    from datetime import datetime, timezone
                    exp_year = int(m.group(3))
                    now_year = datetime.now(timezone.utc).year
                    if exp_year - now_year <= 2:
                        short, color = f"Taken ({m.group(3)})", QColor("#94a3b8")
                    else:
                        short, color = "Active", QColor("#94a3b8")
                else:
                    short, color = "Active", QColor("#94a3b8")
            else:
                short, color = "Active", QColor("#94a3b8")

        elif status_norm in ("", "nodataavailable", "noobjectfound", "free", "notfound", "available", "nomatches", "nomatch"):
            # KEY FIX: empty / 'no match' WHOIS response = domain has dropped and is available to register
            short, color = "Available \u2705", QColor("#4ade80")
            drop_est = "Available now"

        elif "whoiserror" in status_norm or "timeout" in status_norm:
            short, color = "WHOIS err", QColor("#f87171")

        else:
            short, color = status_norm[:18], QColor("#94a3b8")

        # ── Write to table cells ──────────────────────────────────────
        def _set_item_if_present(table, rowmap, col, text, fg=None):
            row = rowmap.get(domain)
            if row is None:
                return
            item = table.item(row, col)
            if item is None:
                item = QTableWidgetItem()
                table.setItem(row, col, item)
            item.setText(text)
            if fg:
                item.setForeground(fg)

        for tbl, rmap in [
            (self.monitor_table, self.monitor_rows),
            (self.rampage_table, self.rampage_rows),
        ]:
            _set_item_if_present(tbl, rmap, COL_WHOIS, short, color)
            _set_item_if_present(tbl, rmap, COL_DROP,  drop_est)

    # ------------------------------------------------------------------
    #  Copy WHOIS results to clipboard
    # ------------------------------------------------------------------

    def copy_whois_results(self):
        """Copy actionable WHOIS results (pendingDelete / Available / Taken / Redemption)
        to clipboard as domain<TAB>status lines — one per row."""
        lines = []
        for domain, row in self.monitor_rows.items():
            whois_item = self.monitor_table.item(row, COL_WHOIS)
            status_text = whois_item.text().strip() if whois_item else ""
            if not status_text or status_text in ("-", "Run WHOIS", "WHOIS err", "Unknown", "Active", "Idle", "Stopped"):
                continue
            lo = status_text.lower()
            if any(k in lo for k in ("pendingdelete", "available", "taken", "redemption")):
                lines.append(f"{domain}\t{status_text}")

        if lines:
            QApplication.clipboard().setText("\n".join(lines))
            self.append_log(
                f"\U0001f4cb Copied {len(lines)} domain(s) to clipboard "
                f"(pendingDelete / Available / Taken / Redemption)."
            )
        else:
            self.append_log("No actionable WHOIS results to copy — run '\U0001f50d WHOIS All' first.")

    # ------------------------------------------------------------------
    #  Remaining handler methods
    # ------------------------------------------------------------------

    def _update_clock(self):
        self.clock_lbl.setText(datetime.now().strftime("%H:%M:%S"))

    def append_log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.append(f"[{ts}] {msg}")
        self.footer_lbl.setText(msg[:80])

    def refresh_stats(self):
        mon_total  = len(self.monitor_rows)
        mon_active = sum(
            1 for d in self.monitor_rows
            if self.monitor_runtime.get(d, {}).get("active", False)
        )
        self.monitor_stats_label.setText(
            f"\U0001f4e1 Monitoring domains: {mon_total} | Active: {mon_active}"
        )

        ram_total = len(self.rampage_rows)
        ram_armed = sum(
            1 for d in self.rampage_rows
            if not self._stop_event_for(d, "rampage") or not self._stop_event_for(d, "rampage").is_set()
        )
        self.rampage_stats_label.setText(
            f"\u26a1 Rampage queue: {ram_total} | Armed: {ram_armed}"
        )

        caught = self.portfolio_table.rowCount()
        total_cost = 0.0
        for r in range(caught):
            item = self.portfolio_table.item(r, 2)
            if item:
                try:
                    total_cost += float(item.text().replace("$", ""))
                except ValueError:
                    pass
        self.p_stats.setText(
            f"\U0001f4e6 Caught: {caught} | Est. Total Spent: ${total_cost:.2f}"
        )

    def _update_status(self, domain, status, color="#93c5fd"):
        self._set_status_in_tables(domain, status, color)

    def _set_status_in_tables(self, domain, status, color="#93c5fd"):
        for table, rowmap in [
            (self.monitor_table, self.monitor_rows),
            (self.rampage_table, self.rampage_rows),
        ]:
            row = rowmap.get(domain)
            if row is None:
                continue
            item = table.item(row, COL_STATUS)
            if item is None:
                item = QTableWidgetItem()
                table.setItem(row, COL_STATUS, item)
            item.setText(status)
            item.setForeground(QColor(color))

    # ── Signal handlers — named to match main.py signal contracts ─────

    def _handle_success(self, domain, result):
        """Slot for signals.success — domain was successfully registered."""
        self._update_status(domain, f"\U0001f7e2 Registered! {result}", "#4ade80")
        self.append_log(f"\u2705 {domain} registered: {result}")
        self._add_to_portfolio(domain)
        if self.settings.get("sound", True):
            QApplication.beep()

    # Keep old name as alias so any internal callers don't break
    _on_success = _handle_success

    def _handle_failure(self, domain, error):
        """Slot for signals.failure — registration attempt failed."""
        self._update_status(domain, f"\U0001f534 Failed: {error}", "#f87171")
        self.append_log(f"\u274c {domain} failed: {error}")

    _on_failure = _handle_failure

    def _on_status_update(self, domain, status):
        color = "#93c5fd"
        sl = status.lower()
        if "available" in sl or "registered" in sl:
            color = "#4ade80"
        elif "fail" in sl or "error" in sl:
            color = "#f87171"
        elif "rampage" in sl or "layer 2" in sl:
            color = "#c4b5fd"
        self._update_status(domain, status, color)

    def _store_next_check(self, domain, ts, mode):
        """Slot for signals.next_check — store and display next check countdown."""
        next_map = self.monitor_next_ts if mode == "monitor" else self.rampage_next_ts
        next_map[domain] = ts

        for table, rowmap in [
            (self.monitor_table, self.monitor_rows),
            (self.rampage_table, self.rampage_rows),
        ]:
            row = rowmap.get(domain)
            if row is None:
                continue
            item = table.item(row, COL_NEXT)
            if item is None:
                item = QTableWidgetItem()
                table.setItem(row, COL_NEXT, item)
            remaining = max(0, int(ts - time.time()))
            item.setText(f"{remaining}s")

    _on_next_check = _store_next_check

    def _handle_premium(self, domain, price, cents):
        """Slot for signals.premium_detect — prompt user about premium pricing."""
        max_prem = self.settings.get("max_premium", 500)
        if max_prem > 0 and price > max_prem:
            self._update_status(domain, f"\U0001f4b0 Premium ${price:.0f} — skipped (>{max_prem})", "#fbbf24")
            self.append_log(f"[PREMIUM] {domain} ${price:.2f} > max ${max_prem} — skipped.")
            return
        msg = (
            f"{domain} is a PREMIUM domain.\n"
            f"Price: ${price:.2f} ({cents} cents)\n\n"
            f"Register anyway?"
        )
        reply = QMessageBox.question(self, "Premium Domain", msg, QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.append_log(f"[PREMIUM] User approved {domain} at ${price:.2f}.")
        else:
            self._update_status(domain, f"\U0001f4b0 Premium ${price:.0f} — skipped", "#fbbf24")
            self.append_log(f"[PREMIUM] {domain} skipped by user.")

    _on_premium_detect = _handle_premium

    def _update_price_col(self, domain, price_str):
        """Slot for signals.price_update — write a price string into COL_PRICE."""
        for table, rowmap in [
            (self.monitor_table, self.monitor_rows),
            (self.rampage_table, self.rampage_rows),
        ]:
            row = rowmap.get(domain)
            if row is None:
                continue
            item = table.item(row, COL_PRICE)
            if item is None:
                item = QTableWidgetItem()
                table.setItem(row, COL_PRICE, item)
            item.setText(price_str)

    def _show_premium_result(self, domain, available, price_cents):
        """Slot for signals.premium_check_result — display premium availability check result."""
        if not available:
            self._update_status(domain, "Unavailable", "#f87171")
            self.append_log(f"[PREMIUM CHECK] {domain} — not available.")
            return
        if price_cents and price_cents > 0:
            price_usd = price_cents / 100.0
            self._update_status(domain, f"\U0001f4b0 Premium ${price_usd:.2f}", "#fbbf24")
            self._update_price_col(domain, f"${price_usd:.2f}")
            self.append_log(f"[PREMIUM CHECK] {domain} available at ${price_usd:.2f} (premium).")
        else:
            self._update_status(domain, "\U0001f7e2 Available", "#4ade80")
            self.append_log(f"[PREMIUM CHECK] {domain} available at standard price.")

    def _on_auto_whois_tick(self, domain, raw):
        self._show_whois_result(domain, raw)

    def _on_whois_progress(self, done, total):
        pct = int(done / total * 100) if total else 100
        self.whois_progress.setValue(pct)
        self.whois_progress.setFormat(f"{done}/{total}" if done < total else "Done")

    def _add_to_portfolio(self, domain):
        price = get_tld_price(domain)
        row = self.portfolio_table.rowCount()
        self.portfolio_table.insertRow(row)
        self.portfolio_table.setItem(row, 0, QTableWidgetItem(domain))
        self.portfolio_table.setItem(row, 1, QTableWidgetItem(datetime.now().strftime("%Y-%m-%d %H:%M")))
        self.portfolio_table.setItem(row, 2, QTableWidgetItem(f"${price:.2f}"))
        self.portfolio_table.setItem(row, 3, QTableWidgetItem("Registered"))
        self.portfolio_table.setItem(row, 4, QTableWidgetItem(""))
        self.refresh_stats()

    def _clear_portfolio(self):
        self.portfolio_table.setRowCount(0)
        self.refresh_stats()

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "caught_domains.csv", "CSV Files (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Domain", "Est. Drop", "Price", "WHOIS", "Status"])
            for domain, row in self.monitor_rows.items():
                cols = []
                for col in (3, COL_DROP, COL_PRICE, COL_WHOIS, COL_STATUS):
                    item = self.monitor_table.item(row, col)
                    cols.append(item.text() if item else "")
                w.writerow(cols)
        self.append_log(f"Exported {len(self.monitor_rows)} domains to {path}")

    def export_portfolio(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Portfolio", "portfolio.csv", "CSV Files (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Domain", "Caught At", "Price Paid", "Status", "Notes"])
            for row in range(self.portfolio_table.rowCount()):
                cols = []
                for col in range(5):
                    item = self.portfolio_table.item(row, col)
                    cols.append(item.text() if item else "")
                w.writerow(cols)
        self.append_log(f"Portfolio exported to {path}")

    def clear_watchlist(self):
        self.monitor_table.setRowCount(0)
        self.monitor_rows.clear()
        self.monitor_next_ts.clear()
        save_watchlist([])
        self.refresh_stats()
        self.append_log("Monitoring list cleared.")

    def generate_ai_prompt(self):
        tokens = re.split(r"[\s,;]+", self.ai_input.toPlainText())
        domains = [normalize_domain(t) for t in tokens if normalize_domain(t)]
        if not domains:
            self.append_log("No domains in AI tab.")
            return
        prompt = (
            "You are a domain investment expert. Analyse the following domains and rank them "
            "by investment potential. For each domain provide: estimated resale value, target industry, "
            "memorability score (1-10), and a one-line verdict.\n\nDomains:\n"
            + "\n".join(f"- {d}" for d in domains)
        )
        QApplication.clipboard().setText(prompt)
        self.ai_preview.setPlainText(prompt)
        self.append_log(f"AI prompt for {len(domains)} domains copied to clipboard.")

    def run_whois_row(self, domain):
        """Queue a single WHOIS lookup for *domain* via the background worker."""
        self.whois_queue.put(domain)
        self.whois_worker_wake.set()

    def _run_whois_manual(self):
        domain = normalize_domain(self.whois_input.text())
        if not domain:
            return
        self.whois_output.setPlainText(f"Querying {domain}...")
        import whois as _w
        def _run():
            try:
                result = _w.whois(domain)
                text = str(result)
            except Exception as ex:
                text = f"Error: {ex}"
            self.signals.whois_manual_result.emit(domain, text)
        threading.Thread(target=_run, daemon=True).start()

    def _on_whois_manual_result(self, domain, text):
        self.whois_output.setPlainText(text)

    def _toggle_auto_whois(self, checked):
        if checked:
            self.whois_auto_btn.setText("\u23f9 Stop")
            self.append_log("Auto-WHOIS monitor started.")
        else:
            self.whois_auto_btn.setText("\u25b6\ufe0f Start")
            self.append_log("Auto-WHOIS monitor stopped.")

    def _toggle_on_top(self, checked):
        from PyQt5.QtCore import Qt as _Qt
        flags = self.windowFlags()
        if checked:
            flags |= _Qt.WindowStaysOnTopHint
        else:
            flags &= ~_Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()
        self._save_setting("always_on_top", checked)

    def _save_setting(self, key, value):
        self.settings[key] = value
        save_settings(self.settings)

    def _on_poll_mode_changed(self, text):
        is_custom = text == "Custom"
        self.custom_secs.setVisible(is_custom)
        self.mode_badge.setText(f"\U0001f7e2 {text}")
        self._wake_monitor_scheduler()

    def _get_poll_interval(self):
        mode_text = self.poll_mode.currentText()
        if mode_text == "Custom":
            return self.custom_secs.value()
        return POLL_MODES.get(mode_text, 60)

    def _on_priority_toggled(self, checked):
        set_priority_enabled(checked)
        self.append_log(f"Priority weighting {'enabled' if checked else 'disabled'}.")

    def _on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show()
            self.raise_()
            self.activateWindow()

    def _on_schedule_timer(self):
        if not self.schedule_check.isChecked():
            return
        target = self.schedule_time.time()
        now    = QTime.currentTime()
        if abs(now.secsTo(target)) <= 30:
            self.start_rampage_all()
            self.append_log("\u23f0 Scheduled Rampage triggered.")

    def _wake_monitor_scheduler(self):
        self.monitor_scheduler_wake.set()

    def _arm_all_autobuy(self):
        from constants import COL_AUTOBUY
        from PyQt5.QtCore import Qt
        count = 0
        for domain, row in self.monitor_rows.items():
            item = self.monitor_table.item(row, COL_AUTOBUY)
            if item and item.checkState() != Qt.Checked:
                item.setCheckState(Qt.Checked)
                count += 1
        self.append_log(f"[AUTO-BUY] Armed {count} domain(s) in Monitoring.")

    def _disarm_all_autobuy(self):
        from constants import COL_AUTOBUY
        from PyQt5.QtCore import Qt
        count = 0
        for domain, row in self.monitor_rows.items():
            item = self.monitor_table.item(row, COL_AUTOBUY)
            if item and item.checkState() == Qt.Checked:
                item.setCheckState(Qt.Unchecked)
                count += 1
        self.append_log(f"[AUTO-BUY] Disarmed {count} domain(s) in Monitoring.")
