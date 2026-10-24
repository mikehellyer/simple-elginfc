"""Persisted user preferences."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Optional

from platformdirs import user_config_dir


@dataclass
class Settings:
    # The tab showing when the app was last closed, so it opens there again.
    tab: int = 0
    # The window's size and place, as Qt's saveGeometry() gives it (hex).
    geometry: str = ""
    # The last opponent looked up on the Head to Head tab.
    h2h_opponent: str = ""
    # Count the clubs an opponent became or merged into as the same opponent
    # (Inverness Caledonian and Thistle with Caledonian Thistle, and so on).
    h2h_related: bool = False


_RANGES = {"tab": (0, 10)}


class SettingsStore:
    def __init__(self, config_path: Optional[Path] = None):
        self._config_path = config_path or Path(user_config_dir("Simple-ElginFC")) / "settings.json"
        self.settings = Settings()
        self.load()

    def update(self, **changes) -> None:
        for name, value in changes.items():
            if not hasattr(self.settings, name):
                raise AttributeError(name)
            setattr(self.settings, name, value)
        self.save()

    def load(self) -> None:
        try:
            data = json.loads(self._config_path.read_text())
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, dict):
            return
        defaults = Settings()
        for f in fields(Settings):
            if f.name not in data:
                continue
            value, default = data[f.name], getattr(defaults, f.name)
            if type(value) is not type(default):
                continue
            if f.name in _RANGES:
                low, high = _RANGES[f.name]
                value = max(low, min(high, value))
            setattr(self.settings, f.name, value)

    def save(self) -> None:
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            self._config_path.write_text(json.dumps(asdict(self.settings), indent=2))
        except OSError:
            pass
