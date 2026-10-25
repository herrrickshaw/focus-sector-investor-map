import importlib.util, os, sys, types

import pytest

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def fake_yf(monkeypatch):
    """Replace yfinance with an in-memory table: ticker -> .info dict. No network, no sleeps."""
    infos = {}

    class Ticker:
        def __init__(self, t):
            self.t = t

        @property
        def info(self):
            if self.t not in infos:
                raise RuntimeError("404 not found")
            return infos[self.t]

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=Ticker))
    monkeypatch.setattr("time.sleep", lambda s: None)
    return infos
