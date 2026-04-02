# api.py
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import API_KEY, API_SECRET, BASE_URL, CONTACT_ID

# ---------------------------------------------------------------------------
# Persistent session — reuses the underlying TCP/TLS connection across all
# calls so each request skips the ~50-100ms handshake cost.  This is the
# single biggest latency win for Rampage mode (sub-1s poll intervals).
#
# Retry policy (transport-level only):
#   - Retries on connection-reset / read errors — NOT on 429 / 4xx / 5xx.
#     Those are handled explicitly by the callers below so the Rampage queue
#     stays in full control of back-off timing.
# ---------------------------------------------------------------------------
_retry = Retry(
    total=3,
    backoff_factor=0.3,          # 0s → 0.3s → 0.6s between socket retries
    status_forcelist=[],          # no automatic HTTP-status retries (handled manually)
    allowed_methods=["GET", "POST"],
    raise_on_status=False,
)
_adapter = HTTPAdapter(
    max_retries=_retry,
    pool_connections=4,           # keep up to 4 host connection pools
    pool_maxsize=16,              # up to 16 live sockets per pool
)

_session = requests.Session()
_session.mount("https://", _adapter)
_session.mount("http://",  _adapter)
_session.headers.update({
    "X-API-Key":    API_KEY,
    "X-API-Secret": API_SECRET,
    "Content-Type": "application/json",
})

# Public alias kept for any code that reads HEADERS directly (read-only).
HEADERS = dict(_session.headers)


# ---------------------------------------------------------------------------
# Registration payload — fixed intent: always 1 year, never auto-renew.
# Changing these values requires an explicit code change, not an accidental
# kwarg, so the behaviour stays auditable and predictable.
# ---------------------------------------------------------------------------
_REGISTRATION_YEARS      = 1      # register for exactly one year
_REGISTRATION_AUTO_RENEW = False   # never auto-renew; user decides manually


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_domain(domain: str) -> dict:
    """
    GET /v1/domains/{domain}/available

    Rate limits: 5/domain/300 s  and  30/user/30 s
    Returns a normalised availability dict consumed by sniper.py.
    """
    try:
        r = _session.get(
            f"{BASE_URL}/domains/{domain}/available",
            timeout=10,
        )

        if r.status_code == 200:
            data = r.json()
            premiums = data.get("premiumPricing", [])
            reg_price = None
            currency = "USD"

            for p in premiums:
                if p.get("operation") == "register":
                    reg_price = p.get("price")
                    currency  = p.get("currency", "USD")
                    break

            return {
                "result":           data.get("result", "unexpectedError"),
                "is_premium":       len(premiums) > 0,
                "premium_price":    reg_price,
                "premium_currency": currency,
                "_status_code":     200,
            }

        if r.status_code == 429:
            return {
                "result":      "rate_limited",
                "retry_after": int(r.headers.get("Retry-After", 60)),
                "_status_code": 429,
            }

        return {
            "result":       "unexpectedError",
            "_status_code": r.status_code,
            "detail":       r.text[:300],
        }

    except requests.exceptions.Timeout:
        return {"result": "timeout", "_status_code": 0}
    except Exception as e:
        return {"result": "error", "detail": str(e), "_status_code": 0}


def register_domain(domain: str) -> dict:
    """
    POST /v1/domains/{domain}

    Always registers for 1 year with no auto-renewal (see module constants
    _REGISTRATION_YEARS and _REGISTRATION_AUTO_RENEW above).
    Rate limit: 30/user/30 s, no per-domain cap.
    Returns a normalised status dict for the Rampage queue.
    """
    payload = {
        "autoRenew": _REGISTRATION_AUTO_RENEW,  # False — user renews manually
        "years":     _REGISTRATION_YEARS,        # 1 year only
        "privacyProtection": {
            "level":       "high",
            "userConsent": True,
        },
        "contacts": {
            "registrant": CONTACT_ID,
            "admin":      CONTACT_ID,
            "tech":       CONTACT_ID,
            "billing":    CONTACT_ID,
        },
    }

    try:
        r = _session.post(
            f"{BASE_URL}/domains/{domain}",
            json=payload,
            timeout=15,
        )

        if r.status_code == 202:
            op_id = r.headers.get("spaceship-async-operationid", "")
            return {
                "status":      "PENDING",
                "operationId": op_id,
                "name":        domain,
                "_status_code": 202,
            }

        if r.status_code == 429:
            return {
                "_status_code": 429,
                "retry_after":  int(r.headers.get("Retry-After", 30)),
            }

        try:
            data = r.json()
        except Exception:
            data = {"detail": r.text[:300]}

        data["_status_code"] = r.status_code
        return data

    except requests.exceptions.Timeout:
        return {"_status_code": 0, "detail": "timeout"}
    except Exception as e:
        return {"_status_code": 0, "detail": str(e)}


def poll_operation(operation_id: str) -> dict:
    """
    GET /v1/async-operations/{operation_id}

    Returns a dict that always contains '_status_code' so callers can
    distinguish transient errors (0 / 5xx) from actual poll results (200)
    and explicit rate-limits (429) — previously all collapsed to {}.
    """
    try:
        r = _session.get(
            f"{BASE_URL}/async-operations/{operation_id}",
            timeout=10,
        )

        if r.status_code == 200:
            data = r.json()
            data["_status_code"] = 200
            return data

        if r.status_code == 429:
            return {
                "_status_code": 429,
                "retry_after":  int(r.headers.get("Retry-After", 30)),
                "status":       "pending",   # treat as still running, not failed
            }

        # 5xx or unexpected — signal a transient error but do NOT mark as failed
        return {
            "_status_code": r.status_code,
            "status":       "pending",
            "detail":       r.text[:300],
        }

    except requests.exceptions.Timeout:
        return {"_status_code": 0, "status": "pending", "detail": "timeout"}
    except Exception as e:
        return {"_status_code": 0, "status": "pending", "detail": str(e)}


# ---------------------------------------------------------------------------
# Backward-compatible aliases
# ---------------------------------------------------------------------------
checkdomain    = check_domain
registerdomain = register_domain
polloperation  = poll_operation
