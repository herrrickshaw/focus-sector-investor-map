"""Load a script from scripts/ as a module with its output locations redirected into tmp_path.

The scripts derive their output directory from __file__ and their inputs from Path.home(),
so executing them as-is would read the real home directory and overwrite the committed
CSVs. Compiling the real source under its real filename keeps coverage attributed to the
repo file while the globals say the script lives under tmp_path.
"""
import pathlib
import sys
import types

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def load_script(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: home))
    (tmp_path / "data").mkdir(exist_ok=True)

    def _load(name):
        real = REPO / "scripts" / name
        ns = {"__name__": f"script_{real.stem}", "__file__": str(real)}
        exec(compile(real.read_text(encoding="utf-8"), str(real), "exec"), ns)
        # The scripts look these up as globals at call time, so rebinding them redirects every
        # read/write into tmp_path (they were computed from the real __file__ at import).
        data = tmp_path / "data"
        for k, v in {"OUT": data, "DATA": data, "ROOT": tmp_path,
                     "CATALOG": data / "focus_sector_global_catalog.csv"}.items():
            if k in ns:
                ns[k] = v
        for k, fname in {"OUT_CSV": None}.items():
            if k in ns:
                ns[k] = data / pathlib.Path(ns[k]).name
        return types.SimpleNamespace(**ns), ns

    _load.home = home
    _load.data = tmp_path / "data"
    return _load


@pytest.fixture
def fake_yf(monkeypatch):
    """Install a fake `yfinance` whose Ticker(t).info comes from a dict (or raises)."""
    state = types.SimpleNamespace(infos={}, calls=[])

    class Ticker:
        def __init__(self, t):
            state.calls.append(t)
            self.t = t

        @property
        def info(self):
            v = state.infos.get(self.t, {})
            if isinstance(v, Exception):
                raise v
            if callable(v):
                return v()
            return v

    mod = types.ModuleType("yfinance")
    mod.Ticker = Ticker
    monkeypatch.setitem(sys.modules, "yfinance", mod)
    return state


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    import time
    monkeypatch.setattr(time, "sleep", lambda s: None)
