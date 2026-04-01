import re
# mixin_monitor.py
# Monitor scheduler loop, WHOIS worker, and all runtime-management helpers
# for DropCatcher.
import time
import threading
from datetime import timezone

from api import check_domain, register_domain
from sniper import poll_until_done
from constants import (
    MONITOR_MIN_PER_DOMAIN_INTERVAL,
    MONITOR_MAX_USER_RPS_DELAY,
    MONITOR_IDLE_SLEEP,
    WHOIS_MIN_SPACING,
    COL_DROP,
    COL_WHOIS,
)
from utils import (
    normalize_domain,
    estimate_drop_date,
    _extract_expiry_from_raw_whois,
    _first_datetime,
    _norm_status,
)


class MonitorMixin:
    """Mixin: monitor scheduler, WHOIS worker, and runtime-state helpers."""

    def _sleep_with_stop(self, stop_event, seconds):
        end = time.time() + max(0.0, seconds)
        while time.time() < end:
            if stop_event.is_set():
                return True
            time.sleep(min(0.25, max(0.01, end - time.time())))
        return stop_event.is_set()

    def _count_active_monitor_domains(self):
        with self.monitor_scheduler_lock:
            return sum(
                1
                for d, st in self.monitor_runtime.items()
                if d in self.monitor_rows and st.get("active")
            )

    def _ensure_monitor_runtime_unlocked(self, domain):
        st = self.monitor_runtime.get(domain)
        if st is None:
            st = {
                "active": False,
                "next_allowed_at": 0.0,
                "last_check_at": 0.0,
                "stop_after_ts": None,
                "inflight": False,
            }
            self.monitor_runtime[domain] = st
        return st

    def _ensure_monitor_runtime(self, domain):
        with self.monitor_scheduler_lock:
            return self._ensure_monitor_runtime_unlocked(domain)

    def _wake_monitor_scheduler(self):
        self._update_monitor_delay_label()
        self.monitor_scheduler_wake.set()

    def _monitor_pick_next_domain(self):
        now = time.time()
        with self.monitor_scheduler_lock:
            for d in list(self.monitor_runtime.keys()):
                if d not in self.monitor_rows:
                    self.monitor_runtime.pop(d, None)

            active = []
            for domain, st in self.monitor_runtime.items():
                if not st.get("active"):
                    continue
                if st.get("stop_after_ts") and now >= st["stop_after_ts"]:
                    st["active"] = False
                    st["inflight"] = False
                    self.monitor_next_ts.pop(domain, None)
                    self.signals.status_update.emit(domain, "Auto-stopped")
                    continue
                active.append((domain, st))

            if not active:
                return None, None

            eligible = [
                (domain, st)
                for domain, st in active
                if not st.get("inflight") and st.get("next_allowed_at", 0.0) <= now
            ]
            if not eligible:
                soonest = min(st.get("next_allowed_at", now + 1) for _, st in active)
                return None, max(MONITOR_IDLE_SLEEP, soonest - now)

            eligible.sort(
                key=lambda pair: (
                    pair[1].get("next_allowed_at", 0.0),
                    pair[1].get("last_check_at", 0.0),
                )
            )
            domain, st = eligible[0]
            st["inflight"] = True
            return domain, 0.0

    def _monitor_scheduler_loop(self):
        while not self.monitor_scheduler_stop.is_set():
            domain, wait_hint = self._monitor_pick_next_domain()
            if domain is None:
                wait = wait_hint if wait_hint is not None else MONITOR_IDLE_SLEEP
                self.monitor_scheduler_wake.wait(wait)
                self.monitor_scheduler_wake.clear()
                continue

            now = time.time()
            if self.monitor_global_backoff_until > now:
                self.monitor_scheduler_wake.wait(
                    min(0.5, self.monitor_global_backoff_until - now)
                )
                self.monitor_scheduler_wake.clear()
                self._mark_monitor_not_inflight(domain)
                continue

            global_gap = self._monitor_global_delay()
            since_last = now - self.monitor_last_request_ts
            if since_last < global_gap:
                self.monitor_scheduler_wake.wait(min(0.5, global_gap - since_last))
                self.monitor_scheduler_wake.clear()
                self._mark_monitor_not_inflight(domain)
                continue

            self._run_monitor_check(domain)

    def _mark_monitor_not_inflight(self, domain):
        with self.monitor_scheduler_lock:
            st = self.monitor_runtime.get(domain)
            if st:
                st["inflight"] = False

    def _monitor_set_next(self, domain, next_ts, status_text=None, status_color=None):
        with self.monitor_scheduler_lock:
            st = self.monitor_runtime.get(domain)
            if st:
                st["inflight"] = False
                st["last_check_at"] = time.time()
                st["next_allowed_at"] = next_ts

        self.monitor_next_ts[domain] = next_ts
        self.signals.next_check.emit(domain, next_ts, "monitor")
        if status_text:
            self._set_status_in_tables(domain, status_text, status_color or "#94a3b8")

    def _run_monitor_check(self, domain):
        now = time.time()
        self.monitor_last_request_ts = now
        cycle_target = self._effective_monitor_domain_interval()
        self.signals.status_update.emit(domain, "Checking availability...")

        try:
            info = check_domain(domain) or {}
            result = str(info.get("result", "")).lower()

            if result == "available":
                if info.get("is_premium") and info.get("premium_price"):
                    try:
                        price = float(info.get("premium_price") or 0)
                    except Exception:
                        price = 0.0
                    currency = info.get("premium_currency", "USD")
                    with self.monitor_scheduler_lock:
                        st = self.monitor_runtime.get(domain)
                        if st:
                            st["active"] = False
                            st["inflight"] = False
                    self.monitor_next_ts.pop(domain, None)
                    self.signals.premium_detect.emit(domain, price, currency)
                    self._wake_monitor_scheduler()
                    return

                # ── Two-layer Auto-Buy gate ───────────────────────────────────
                # Both the global checkbox AND the per-row toggle must be ON.
                if not self.domain_autobuy_enabled(domain):
                    nxt = now + cycle_target
                    self._monitor_set_next(
                        domain, nxt,
                        "\u2705 Available (Auto-Buy OFF — not purchasing)",
                        "#4ade80",
                    )
                    self._wake_monitor_scheduler()
                    return
                # ─────────────────────────────────────────────────────────────

                self.signals.status_update.emit(domain, "Available - registering...")
                reg = register_domain(domain) or {}

                with self.monitor_scheduler_lock:
                    st = self.monitor_runtime.get(domain)
                    if st:
                        st["active"] = False
                        st["inflight"] = False
                self.monitor_next_ts.pop(domain, None)

                code = int(reg.get("_status_code", 0) or 0)
                status = str(reg.get("status", "")).upper()

                if code == 202 or status == "PENDING":
                    op_id = reg.get("operationId", "")
                    self.signals.status_update.emit(domain, "Registration submitted - waiting for confirmation...")
                    poll_until_done(
                        domain=domain,
                        op_id=op_id,
                        on_status=lambda d, s: self.signals.status_update.emit(d, s),
                        on_success=lambda d, r: self.signals.success.emit(d, r),
                        on_failure=lambda d, e: self.signals.failure.emit(d, e),
                        stop_event=None,
                        on_next_check=lambda d, ts: self.signals.next_check.emit(d, ts, "monitor"),
                    )
                    self._wake_monitor_scheduler()
                    return

                if reg.get("name"):
                    self.signals.success.emit(domain, reg)
                else:
                    detail = str(
                        reg.get("detail") or reg.get("message") or "Registration failed"
                    )
                    self.signals.failure.emit(domain, detail)
                self._wake_monitor_scheduler()
                return

            if result == "unavailable":
                nxt = now + cycle_target
                self._monitor_set_next(
                    domain, nxt, "Still registered - queued retry...", "#94a3b8"
                )
                self._wake_monitor_scheduler()
                return

            if result == "ratelimited":
                retry_after = (
                    info.get("retry_after")
                    or info.get("retryAfter")
                    or max(30, int(cycle_target))
                )
                try:
                    retry_after = int(float(retry_after))
                except Exception:
                    retry_after = max(30, int(cycle_target))
                wait = max(retry_after, int(cycle_target))
                self.monitor_global_backoff_until = max(
                    self.monitor_global_backoff_until,
                    time.time() + wait,
                )
                nxt = time.time() + wait
                self._monitor_set_next(
                    domain, nxt, f"Rate-limited - cooling down {wait}s", "#fbbf24"
                )
                self._wake_monitor_scheduler()
                return

            if result:
                nxt = now + cycle_target
                self._monitor_set_next(domain, nxt, result, "#93c5fd")
                self._wake_monitor_scheduler()
                return

            nxt = now + cycle_target
            self._monitor_set_next(
                domain, nxt, "Unknown response - queued retry...", "#fbbf24"
            )
            self._wake_monitor_scheduler()

        except Exception as e:
            nxt = time.time() + cycle_target
            self._monitor_set_next(
                domain, nxt, f"Monitor error: {str(e)[:80]}", "#f87171"
            )
            self._wake_monitor_scheduler()

    def _enqueue_whois(self, domain, mode):
        domain = normalize_domain(domain)
        if not domain:
            return
        key = f"{mode}:{domain}"
        with self.whois_queue_lock:
            if key in self.whois_pending:
                return
            self.whois_pending.add(key)
            self.whois_queue.append((domain, mode))
        self.whois_worker_wake.set()

    def run_whois_row(self, domain):
        self._set_item_if_present(
            self.monitor_table,
            self.monitor_rows,
            domain,
            COL_WHOIS,
            self._center_item("...", "#93c5fd"),
        )
        self._set_item_if_present(
            self.monitor_table,
            self.monitor_rows,
            domain,
            COL_DROP,
            self._center_item("...", "#93c5fd"),
        )
        self._set_item_if_present(
            self.rampage_table,
            self.rampage_rows,
            domain,
            COL_WHOIS,
            self._center_item("...", "#93c5fd"),
        )
        self._set_item_if_present(
            self.rampage_table,
            self.rampage_rows,
            domain,
            COL_DROP,
            self._center_item("...", "#93c5fd"),
        )
        self._enqueue_whois(domain, "row")

    def _fetch_whois(self, domain, mode):
        try:
            import whois as whoislib

            expiry = None
            registrar = "Unknown"
            status = None

            try:
                w = whoislib.whois(domain)
                status = w.status
                expiry = getattr(w, "expiration_date", None)
                registrar = getattr(w, "registrar", "Unknown") or "Unknown"
            except Exception as exc:
                raw = str(exc)
                statuses = re.findall(r"Domain Status:\s*(.+)", raw, re.IGNORECASE)
                status = statuses if statuses else "pendingDelete"
                scrubbed = _extract_expiry_from_raw_whois(raw)
                if scrubbed:
                    expiry = scrubbed
                regm = re.search(r"Registrar:\s*(.+)", raw, re.IGNORECASE)
                registrar = regm.group(1).strip() if regm else "Unknown"

            if isinstance(status, list):
                status_str = ", ".join(str(s) for s in status)
            else:
                status_str = str(status) if status else "unknown"

            expiry = _first_datetime(expiry)
            if expiry is not None and expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            expiry_display = str(expiry)[:10] if expiry else "Unknown"

            tld = domain.rsplit(".", 1)[-1] if "." in domain else "com"
            drop_est = estimate_drop_date(expiry, status_str, tld)
            status_norm = _norm_status(status_str)

            result = (
                f"Domain: {domain}\n"
                f"Registrar: {registrar}\n"
                f"Expires: {expiry_display}\n"
                f"Est. Drop: {drop_est}\n"
                f"Status: {status_str}"
            )
            if "pendingdelete" in status_norm:
                result += "\n\nDrop phase detected."
            elif any(
                k in status_norm
                for k in ("redemptionperiod", "pendingrenewaldeletion", "redemption")
            ):
                result += "\n\nRedemption or pre-drop phase."
            elif "active" in status_norm or status_norm == "ok":
                result += "\n\nActive - likely not near drop."

            self.signals.whois_result.emit(
                f"{domain}|{mode}|{drop_est}|{status_norm}", result
            )

        except Exception as e:
            self.signals.whois_result.emit(
                f"{domain}|{mode}|-|whoiserror",
                f"Error: {e}",
            )

    def _whois_worker_loop(self):
        while not self.whois_worker_stop.is_set():
            job = None
            with self.whois_queue_lock:
                if self.whois_queue:
                    job = self.whois_queue.pop(0)

            if not job:
                self.whois_worker_wake.wait(0.5)
                self.whois_worker_wake.clear()
                continue

            domain, mode = job
            gap = time.time() - self.whois_last_request_ts
            if gap < WHOIS_MIN_SPACING:
                if self.whois_worker_stop.wait(WHOIS_MIN_SPACING - gap):
                    break

            self.whois_last_request_ts = time.time()
            self._fetch_whois(domain, mode)

            with self.whois_queue_lock:
                self.whois_pending.discard(f"{mode}:{domain}")

    def _toggle_auto_whois(self, checked):
        secs = self._whois_interval_value()
        self.whois_interval_secs = secs
        if checked:
            self.whois_remaining = secs
            self.whois_timer.start(secs * 1000)
            self.whois_countdown_timer.start(1000)
            self.whois_auto_btn.setText("\u23f9 Stop")
            self.append_log(f"Auto WHOIS monitor started every {secs}s.")
            self._auto_whois_tick()
        else:
            self.whois_timer.stop()
            self.whois_countdown_timer.stop()
            self.whois_progress.setValue(100)
            self.whois_progress.setFormat("Idle")
            self.whois_auto_btn.setText("\u25b6\ufe0f Start")
            self.append_log("Auto WHOIS monitor stopped.")

    def _auto_whois_tick(self):
        self.whois_remaining = self.whois_interval_secs
        seen = set()
        for d in list(self.monitor_rows.keys()) + list(self.rampage_rows.keys()):
            if d not in seen:
                seen.add(d)
                self._enqueue_whois(d, "auto")
