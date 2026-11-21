import json
import os

DATA_DIR = os.path.join(os.path.expanduser("~"), ".pulse_player")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")

DEFAULT_CONFIG = {
    "active_playlist": "Default",
    "favorites": [],
    "accent": "#c0392b",
    "viz_bars": 20,
    "always_on_top": True,
    "shuffle": False,
    "volume": 0.7,
    "last_track": None,
    "last_position": 0,
    "window_x": None,
    "window_y": None,
    "music_dir": "D:\\Music",
}


def _ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def load():
    _ensure_dir()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for key, val in DEFAULT_CONFIG.items():
                if key not in data:
                    data[key] = val
            return data
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save(config):
    _ensure_dir()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
