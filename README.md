# domain-snipe

A high-performance desktop app for monitoring expiring domains and sniping them the moment they drop — built in Python with PyQt5 and the [Spaceship API](https://www.spaceship.com/account/api-management/).

![Python](https://img.shields.io/badge/python-3.10%2B-blue) ![PyQt5](https://img.shields.io/badge/GUI-PyQt5-green) ![Status](https://img.shields.io/badge/status-active%20development-orange)

---

## Features

- **Monitor Mode** — Continuously polls domains at configurable intervals (Conservative 2 min → Aggressive 10 s) and alerts you the instant availability changes.
- **Rampage Mode** — Sub-1-second polling loop that fires a registration request the moment a domain becomes available. Uses a weighted priority queue so your most-wanted domains always get first-in-line treatment.
- **Bulk Import** — Add domains via manual entry, `.txt` file import, or clipboard paste (newline / comma / semicolon separated).
- **Auto-Buy** — Optional per-domain flag that triggers immediate registration without any manual confirmation.
- **Drop Time Reference** — Built-in drop window table for `.com`, `.net`, `.org`, `.info`, `.de`, `.io` so you know exactly when to start Rampage.
- **WHOIS Lookup** — One-click WHOIS from any table row.
- **Persistent Watchlist** — Your monitor list and Rampage queue are saved locally and restored on next launch.
- **System Tray** — Minimises to tray; desktop notifications on registration success or failure.
- **Dark UI** — Clean, low-distraction interface designed for long sniping sessions.

---

## Requirements

- Python **3.10+**
- A [Spaceship](https://www.spaceship.com/) account with API access enabled
- A Spaceship **Contact ID** (used as the registrant for all purchases)

### Python dependencies

```
PyQt5>=5.15
requests>=2.31
```

Install with:

```bash
pip install PyQt5 requests
```

> A `requirements.txt` is on the roadmap — see [ROADMAP.md](ROADMAP.md).

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/Psmith23434/domain-snipe.git
cd domain-snipe
```

### 2. Configure your API credentials

Open `config.py` and fill in your values:

```python
API_KEY    = "your_spaceship_api_key"
API_SECRET = "your_spaceship_api_secret"
BASE_URL   = "https://spaceship.dev/api/v1"
CONTACT_ID = "your_contact_id"   # looks like: 1ZdMXpapqp9sle5dl8BlppTJXAzf5
```

**How to find your credentials:**
- API Key & Secret → [spaceship.com/account/api-management](https://www.spaceship.com/account/api-management/)
- Contact ID → In the Spaceship dashboard under *Contacts*, or run `get_contact_id()` in `api.py` once.

> ⚠️ **Never commit `config.py` with real credentials.** A `.env`-based credential system is on the roadmap.

### 3. Launch

```bash
python main.py
```

---

## Usage

### Monitor Mode

1. Type (or paste) a domain into the input field and click **Add**, or use **Import** to load a `.txt` list.
2. Select domains with the checkboxes and click **Start Monitoring**.
3. Choose your poll interval from the dropdown (default: Normal 60 s).
4. When a domain becomes available, it is highlighted and optionally promoted to Rampage automatically.

### Rampage Mode

1. Add domains to the Rampage queue (manually or by promoting checked Monitor domains).
2. Set your desired poll interval — **Rampage (1 s)** is the fastest.
3. Click **Start Rampage** for checked domains.
4. The app fires a registration attempt the moment the domain responds as available. If the API returns `202 Accepted`, it polls the async operation until confirmed.

### Auto-Buy (🎯)

Toggle the 🎯 icon on any row in either table. With Auto-Buy enabled, the app will register the domain immediately on drop detection without waiting for manual confirmation. Use with caution — charges your Spaceship account.

---

## Architecture

| File | Role |
|---|---|
| `main.py` | App entry point, `QApplication`, signal definitions, `DropCatcher` class assembly |
| `api.py` | Spaceship HTTP client — `check_domain`, `register_domain`, `poll_operation` |
| `sniper.py` | `RampageQueue` scheduler, `poll_until_done` async poller, `snipe_domain` entry point |
| `mixin_monitor.py` | Background monitor scheduler (condition-variable loop) |
| `mixin_actions.py` | Domain add / remove / start / stop / queue actions |
| `mixin_builders.py` | All Qt widget construction and layout |
| `mixin_handlers.py` | Qt signal handlers; all UI updates |
| `mixin_tables.py` | Table row creation, status updates, drag-and-drop reorder |
| `persistence.py` | Watchlist and Rampage queue save / load (JSON) |
| `constants.py` | TLD prices, drop windows, column indices, timing constants |
| `utils.py` | `normalize_domain`, `format_price`, `format_countdown` |
| `widgets.py` | Custom Qt widget subclasses |
| `config.py` | API credentials (local only — do not commit) |

---

## Known Issues & Roadmap

See **[ROADMAP.md](ROADMAP.md)** for the full list of open bugs and planned improvements.

---

## License

MIT
