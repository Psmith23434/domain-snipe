# utils.py
import re
from datetime import datetime, timedelta, timezone

from constants import TLD_PRICES, TLD_DROP_WINDOWS, DROP_RULES


def normalize_domain(value):
    if isinstance(value, dict):
        value = value.get("domain") or value.get("name") or value.get("fqdn") or value.get("value") or ""
    value = str(value or "").strip().lower()
    return value if value and "." in value else ""


def get_tld_price(domain):
    tld = domain.rsplit(".", 1)[-1].lower() if "." in domain else ""
    price = TLD_PRICES.get(tld)
    return f"${price:.2f}" if price is not None else "-"


def get_drop_window(domain):
    tld = domain.rsplit(".", 1)[-1].lower() if "." in domain else ""
    return TLD_DROP_WINDOWS.get(tld, "-")


def _norm_status(s):
    return re.sub(r"[\s_]+", "", str(s or "").lower())


def _first_datetime(value):
    if isinstance(value, list):
        for v in value:
            if isinstance(v, datetime):
                value = v
                break
        else:
            value = value[0] if value else None
    return value if isinstance(value, datetime) else None


def _drop_rule(tld):
    return DROP_RULES.get((tld or "").lower(), DROP_RULES["default"])


def _extract_expiry_from_raw_whois(raw):
    patterns = [
        r"Registry Expiry Date:\s+(\S+)",
        r"Registrar Registration Expiration Date:\s+(\S+)",
        r"Expiration Date:\s+(\S+)",
        r"paid-till:\s+(\S+)",
    ]
    for pat in patterns:
        m = re.search(pat, raw, re.IGNORECASE)
        if not m:
            continue
        val = m.group(1).strip()
        for candidate in (val, val.replace("Z", "+00:00"), val + "T00:00:00+00:00"):
            try:
                return datetime.fromisoformat(candidate)
            except Exception:
                pass
        for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
            try:
                return datetime.strptime(val[:10], fmt).replace(tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def estimate_drop_date(expiry_date, status_str, tld="com"):
    try:
        now = datetime.now(timezone.utc)
        status_norm = _norm_status(status_str)
        expiry = _first_datetime(expiry_date)
        if expiry is not None and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)

        rule = _drop_rule(tld)
        low = rule["low"]
        high = rule["high"]
        pd_days = rule["pending_delete_days"]

        def fmt_range(a, b, prefix="~"):
            if a.date() == b.date():
                return f"{prefix}{a.strftime('%d.%m.%Y')}"
            return f"{prefix}{a.strftime('%d.%m')}–{b.strftime('%d.%m.%Y')}"

        if "pendingdelete" in status_norm:
            if expiry is not None:
                earliest = expiry + timedelta(days=low)
                latest = expiry + timedelta(days=high)
                return f"🔥 {fmt_range(earliest, latest)} (pendingDelete)"
            fallback = now + timedelta(days=pd_days)
            return f"🔥 ~{fallback.strftime('%d.%m.%Y')} ({pd_days}d est.)"

        if any(k in status_norm for k in ("redemptionperiod", "pendingrenewaldeletion", "redemption")):
            if expiry is not None:
                earliest = expiry + timedelta(days=low)
                latest = expiry + timedelta(days=high)
                return f"⚠️ {fmt_range(earliest, latest)}"
            return "⚠️ Redemption / pre-drop"

        if expiry is not None:
            if expiry > now:
                return f"- (active, exp {expiry.strftime('%d.%m.%Y')})"
            earliest = expiry + timedelta(days=low)
            latest = expiry + timedelta(days=high)
            return fmt_range(earliest, latest)

    except Exception as e:
        return f"- (err: {str(e)[:25]})"
    return "-"