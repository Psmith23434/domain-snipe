# sniper.py
import time
import threading

try:
    from api import check_domain as _check_domain, register_domain as _register_domain, poll_operation as _poll_operation
except ImportError:
    from api import checkdomain as _check_domain, registerdomain as _register_domain, polloperation as _poll_operation


POLL_MODES = {
    "Conservative (2 min)": 120,
    "Normal (60s)":          60,
    "Fast (30s)":            30,
    "Aggressive (10s)":      10,
    "Rampage (1s)":           1,
    "Custom":                 0,
}

POLLMODES = POLL_MODES

# ---------------------------------------------------------------------------
# Async-operation polling constants
#   ASYNC_POLL_INTERVAL     — seconds between each status check
#   ASYNC_POLL_MAX_ATTEMPTS — hard ceiling on *successful* 200-status polls
#                             before we give up (200 × 5s = ~10 min max wait)
#   Transient errors (network, 429, 5xx) never burn through this counter;
#   only real "pending" responses from the API count as an attempt.
# ---------------------------------------------------------------------------
ASYNC_POLL_INTERVAL     = 5
ASYNC_POLL_MAX_ATTEMPTS = 120   # was hard-coded 24; raised to 120 (~10 min)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _noop(*args, **kwargs):
    return None


def _status_code(data):
    try:
        return int(
            data.get("_status_code", data.get("statuscode", data.get("status_code", 0))) or 0
        )
    except Exception:
        return 0


def _retry_after(data, default=30):
    try:
        return int(
            data.get("retry_after", data.get("retryafter", data.get("retryAfter", default))) or default
        )
    except Exception:
        return default


def _detail(data, default=""):
    return str(
        data.get("detail", "")
        or data.get("message", "")
        or data.get("error", "")
        or default
    ).strip()


def _sleep_with_stop(stop_event, seconds):
    end = time.time() + max(0.0, float(seconds))
    while time.time() < end:
        if stop_event and stop_event.is_set():
            return True
        time.sleep(min(0.25, max(0.01, end - time.time())))
    return bool(stop_event and stop_event.is_set())


# ---------------------------------------------------------------------------
# Async-operation poller
# ---------------------------------------------------------------------------

def poll_until_done(
    domain,
    op_id,
    on_status,
    on_success,
    on_failure,
    stop_event=None,
    on_next_check=None,
    max_attempts=None,
    poll_interval=None,
):
    """
    Poll /async-operations/{op_id} until the operation reaches a terminal
    state (success / failed) or the attempt limit is exceeded.

    Counting rules — only a genuine HTTP-200 "pending" response counts as an
    attempt.  Transient errors (network timeout, 5xx, 429) do NOT advance the
    counter so a noisy API cannot accidentally exhaust the budget.
    """
    if not op_id:
        on_success(domain, {"name": domain})
        return

    max_attempts  = max_attempts  or ASYNC_POLL_MAX_ATTEMPTS
    poll_interval = poll_interval or ASYNC_POLL_INTERVAL
    attempts      = 0

    while attempts < max_attempts:
        if stop_event and stop_event.is_set():
            return

        if on_next_check:
            try:
                on_next_check(domain, time.time() + poll_interval)
            except Exception:
                pass

        if _sleep_with_stop(stop_event, poll_interval):
            return

        try:
            op = _poll_operation(op_id) or {}
        except Exception as e:
            # Should not happen (api.py catches internally), but guard anyway
            on_status(domain, f"Async poll error: {e}")
            continue  # transient — do NOT count

        code = _status_code(op)

        # --- Rate-limited: back off by whatever the API asks, then retry ---
        if code == 429:
            wait = max(poll_interval, _retry_after(op, poll_interval))
            on_status(domain, f"Async poll rate-limited — waiting {wait}s")
            _sleep_with_stop(stop_event, wait)
            continue  # transient — do NOT count

        # --- Transient server / network error: log detail, retry silently ---
        if code != 200:
            detail = _detail(op, f"HTTP {code}")
            on_status(domain, f"Async poll error ({detail}) — retrying...")
            continue  # transient — do NOT count

        # --- We have a clean 200 response; inspect the operation status ---
        st = str(op.get("status", "unknown")).lower()
        on_status(domain, f"Async: {st}...")

        if st == "success":
            on_success(domain, op)
            return

        if st == "failed":
            on_failure(domain, _detail(op, "Async registration failed"))
            return

        # Still "pending" (or unknown status string) — count this attempt
        attempts += 1

    on_failure(
        domain,
        f"Async timed out after {max_attempts} polls (~{max_attempts * poll_interval}s)"
        " — check your Spaceship dashboard"
    )


# ---------------------------------------------------------------------------
# Rampage Queue
# ---------------------------------------------------------------------------

class RampageQueue:
    PERMANENT_ERRORS = (
        "invalid",
        "not supported",
        "tldnotsupported",
        "invaliddomainname",
        "premium",
        "not available for registration",
    )

    def __init__(self):
        self.lock             = threading.Lock()
        self.domains          = {}
        self.running          = False
        self.priority_enabled = False

    def register(
        self,
        domain,
        on_status=None,
        on_success=None,
        on_failure=None,
        on_next_check=None,
        stop_event=None,
        row_index=999,
    ):
        stop_event   = stop_event or threading.Event()
        start_worker = False

        with self.lock:
            self.domains[domain] = {
                "on_status":    on_status    or _noop,
                "on_success":   on_success   or _noop,
                "on_failure":   on_failure   or _noop,
                "on_next_check": on_next_check or _noop,
                "stop_event":   stop_event,
                "row_index":    row_index,
            }
            if not self.running:
                self.running = True
                start_worker = True

        if start_worker:
            threading.Thread(target=self.loop, daemon=True).start()

        return stop_event

    def unregister(self, domain):
        with self.lock:
            self.domains.pop(domain, None)

    def update_row(self, domain, row_index):
        with self.lock:
            if domain in self.domains:
                self.domains[domain]["row_index"] = row_index

    def set_priority_enabled(self, enabled):
        with self.lock:
            self.priority_enabled = bool(enabled)

    def _cleanup_stopped(self):
        with self.lock:
            stopped = [d for d, info in self.domains.items() if info["stop_event"].is_set()]
            for d in stopped:
                self.domains.pop(d, None)
            if not self.domains:
                self.running = False
                return False
            return True

    def _build_round(self):
        with self.lock:
            active = [
                (domain, info.get("row_index", 999))
                for domain, info in self.domains.items()
                if not info["stop_event"].is_set()
            ]
            priority_enabled = self.priority_enabled

        active.sort(key=lambda x: x[1])

        seq = []
        for idx, (domain, _) in enumerate(active):
            if priority_enabled:
                slots = 3 if idx == 0 else 2 if idx == 1 else 1
            else:
                slots = 1
            seq.extend([domain] * slots)
        return seq

    def _get_info(self, domain):
        with self.lock:
            return self.domains.get(domain)

    def loop(self):
        idx = 0

        while True:
            if not self._cleanup_stopped():
                return

            seq = self._build_round()
            if not seq:
                time.sleep(0.5)
                continue

            if idx >= len(seq):
                idx = 0

            domain = seq[idx]
            idx   += 1

            info = self._get_info(domain)
            if not info:
                time.sleep(0.25)
                continue

            stop_event    = info["stop_event"]
            if stop_event.is_set():
                continue

            on_status     = info["on_status"]
            on_success    = info["on_success"]
            on_failure    = info["on_failure"]
            on_next_check = info["on_next_check"]

            try:
                try:
                    on_next_check(domain, time.time() + 1)
                except Exception:
                    pass

                reg    = _register_domain(domain) or {}
                code   = _status_code(reg)
                status = str(reg.get("status", "")).upper()

                if code == 202 or status == "PENDING":
                    on_status(domain, "Registration submitted...")
                    stop_event.set()
                    poll_until_done(
                        domain,
                        reg.get("operationId", ""),
                        on_status,
                        on_success,
                        on_failure,
                        stop_event=stop_event,
                        on_next_check=on_next_check,
                    )
                    continue

                if code == 429:
                    wait = max(1, _retry_after(reg, 30))
                    on_status(domain, f"Rate-limited — wait {wait}s")
                    _sleep_with_stop(stop_event, wait)
                    continue

                if reg.get("name"):
                    stop_event.set()
                    on_success(domain, reg)
                    continue

                detail       = _detail(reg, "Not dropped yet - retrying...")
                detail_lower = detail.lower()

                if code and 400 <= code < 500 and any(p in detail_lower for p in self.PERMANENT_ERRORS):
                    stop_event.set()
                    on_failure(domain, detail or "Permanent error")
                elif code and code >= 500:
                    on_status(domain, detail or "Server error - retrying...")
                else:
                    on_status(domain, detail or "Not dropped yet - retrying...")

            except Exception as e:
                if not stop_event.is_set():
                    on_status(domain, f"Rampage error: {e}")

            _sleep_with_stop(stop_event, 1)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

rampage_queue = RampageQueue()


def set_priority_enabled(enabled: bool):
    rampage_queue.set_priority_enabled(enabled)


def update_domain_row(domain: str, row_index: int):
    rampage_queue.update_row(domain, row_index)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def snipe_domain(
    domain,
    on_status=None,
    on_success=None,
    on_failure=None,
    on_premium=None,
    on_next_check=None,
    poll_interval=60,
    rampage=False,
    row_index=999,
    stop_event=None,
    auto_buy=False,
    **legacy_kwargs,
):
    # Legacy camelCase kwarg resolution — kept intact until main.py is updated
    on_status     = on_status     or legacy_kwargs.get("onstatus")     or _noop
    on_success    = on_success    or legacy_kwargs.get("onsuccess")    or _noop
    on_failure    = on_failure    or legacy_kwargs.get("onfailure")    or _noop
    on_premium    = on_premium    or legacy_kwargs.get("onpremium")    or _noop
    on_next_check = on_next_check or legacy_kwargs.get("onnextcheck")  or _noop

    poll_interval = legacy_kwargs.get("pollinterval", poll_interval)
    rampage       = legacy_kwargs.get("rampage",      rampage)
    row_index     = legacy_kwargs.get("rowindex",     row_index)
    stop_event    = stop_event    or legacy_kwargs.get("stopevent")    or threading.Event()
    auto_buy      = legacy_kwargs.get("autobuy",      auto_buy)

    if rampage:
        on_status(domain, "Rampage queued...")
        return rampage_queue.register(
            domain=domain,
            on_status=on_status,
            on_success=on_success,
            on_failure=on_failure,
            on_next_check=on_next_check,
            stop_event=stop_event,
            row_index=row_index,
        )

    interval = max(1, int(poll_interval or 60))

    if not auto_buy:
        on_status(domain, "Monitoring is handled by main.py")
        try:
            on_next_check(domain, time.time() + interval)
        except Exception:
            pass
        return stop_event

    while not stop_event.is_set():
        try:
            try:
                on_next_check(domain, time.time() + interval)
            except Exception:
                pass

            info   = _check_domain(domain) or {}
            result = str(info.get("result", "")).lower()

            if result == "available":
                if info.get("is_premium") and info.get("premium_price"):
                    try:
                        price = float(info.get("premium_price") or 0)
                    except Exception:
                        price = 0.0
                    currency = info.get("premium_currency", "USD")
                    stop_event.set()
                    on_premium(domain, price, currency)
                    return stop_event

                on_status(domain, "Available - registering...")
                reg    = _register_domain(domain) or {}
                code   = _status_code(reg)
                status = str(reg.get("status", "")).upper()

                if code == 202 or status == "PENDING":
                    stop_event.set()
                    poll_until_done(
                        domain,
                        reg.get("operationId", ""),
                        on_status,
                        on_success,
                        on_failure,
                        stop_event=stop_event,
                        on_next_check=on_next_check,
                    )
                    return stop_event

                if reg.get("name"):
                    stop_event.set()
                    on_success(domain, reg)
                    return stop_event

                if code == 429:
                    wait = max(1, _retry_after(reg, 30))
                    on_status(domain, f"Rate-limited - wait {wait}s")
                    if _sleep_with_stop(stop_event, wait):
                        return stop_event
                    continue

                stop_event.set()
                on_failure(domain, _detail(reg, "Registration failed"))
                return stop_event

            elif result == "unavailable":
                on_status(domain, "Still registered - retrying...")

            elif result in ("rate_limited", "ratelimited"):
                wait = max(1, _retry_after(info, max(30, interval)))
                on_status(domain, f"Rate-limited - wait {wait}s")
                if _sleep_with_stop(stop_event, wait):
                    return stop_event
                continue

            elif result:
                on_status(domain, f"{result} - retrying...")

            else:
                on_status(domain, "Unknown response - retrying...")

        except Exception as e:
            if not stop_event.is_set():
                on_status(domain, f"Monitor error: {e}")

        if _sleep_with_stop(stop_event, interval):
            break

    return stop_event


# ---------------------------------------------------------------------------
# Backward-compatible aliases (all preserved)
# ---------------------------------------------------------------------------

def setpriorityenabled(enabled: bool):
    set_priority_enabled(enabled)


def updatedomainrow(domain: str, rowindex: int):
    update_domain_row(domain, rowindex)


def snipedomain(
    domain,
    onstatus=None,
    onsuccess=None,
    onfailure=None,
    onpremium=None,
    onnextcheck=None,
    pollinterval=60,
    rampage=False,
    rowindex=999,
    stopevent=None,
    autobuy=False,
):
    return snipe_domain(
        domain=domain,
        on_status=onstatus,
        on_success=onsuccess,
        on_failure=onfailure,
        on_premium=onpremium,
        on_next_check=onnextcheck,
        poll_interval=pollinterval,
        rampage=rampage,
        row_index=rowindex,
        stop_event=stopevent,
        auto_buy=autobuy,
    )


__all__ = [
    "POLL_MODES",
    "POLLMODES",
    "ASYNC_POLL_INTERVAL",
    "ASYNC_POLL_MAX_ATTEMPTS",
    "poll_until_done",
    "set_priority_enabled",
    "setpriorityenabled",
    "update_domain_row",
    "updatedomainrow",
    "snipe_domain",
    "snipedomain",
]
