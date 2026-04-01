# constants.py

TLD_PRICES = {
    "com": 9.98,
    "net": 9.98,
    "org": 9.98,
    "de": 7.98,
    "io": 39.98,
    "co": 24.98,
    "info": 3.98,
    "biz": 7.98,
    "ai": 79.98,
    "app": 19.98,
    "dev": 12.98,
    "shop": 19.98,
    "online": 4.98,
    "site": 4.98,
    "club": 4.98,
}

DROP_RULES = {
    "default": {"low": 65, "high": 80, "pending_delete_days": 5},
    "de": {"low": 31, "high": 31, "pending_delete_days": 1},
}

TLD_DROP_WINDOWS = {
    "com": "20:00-21:00",
    "net": "20:00-21:00",
    "org": "16:30-17:30",
    "info": "17:30-17:40",
    "de": "Day 31 (random)",
    "io": "~18:00-20:00",
}

DROP_TIMES_TABLE = [
    (".com / .net", "18:00-19:00 UTC", "20:00-21:00", "Verisign daily window; most competitive."),
    (".org",        "14:30-15:30 UTC", "16:30-17:30", "PIR managed; daily drop, medium competition."),
    (".info",       "15:30-15:40 UTC", "17:30-17:40", "Short window, lower competition."),
    (".de",         "Day 31 (random)", "Unpredictable", "DENIC releases at random time on day 31."),
    (".io",         "~16:00-18:00 UTC", "~18:00-20:00", "Approximate window only."),
]

# Table column indices
COL_DRAG    = 0
COL_SNIPE   = 1   # selection checkbox  (✓)
COL_AUTOBUY = 2   # per-domain auto-buy (🎯)
COL_DOMAIN  = 3
COL_DROP    = 4
COL_PRICE   = 5
COL_WHOIS   = 6
COL_STATUS  = 7
COL_NEXT    = 8
COL_ACT     = 9

# Timing constants
MONITOR_MIN_PER_DOMAIN_INTERVAL = 60.0
MONITOR_MAX_USER_RPS_DELAY      = 1.0
MONITOR_IDLE_SLEEP              = 0.20
WHOIS_MIN_SPACING               = 2.0
