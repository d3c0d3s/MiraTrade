from pathlib import Path

from mirabot.cli import pipeline
from mirabot.edge import benjamini_hochberg
from mirabot.synthetic import make_market

import pandas as pd


def _run(tmp_path: Path, drift: float, seed: int = 7):
    prices, insiders, flow = make_market(seed=seed, drift_after_signal=drift)
    return pipeline(prices, insiders, flow, prices["SPY"].index[-90], tmp_path)


def test_recovers_planted_edge(tmp_path):
    res = _run(tmp_path, drift=0.004)
    validated = res["rules"][res["rules"]["validated"]]
    assert validated["rule"].str.contains("ins:|event:insider_buy|flow:|event:flow").any()
    assert (tmp_path / "edge_report.md").read_text().startswith("# MiraBot edge report")


def test_no_signal_edge_in_pure_noise(tmp_path):
    res = _run(tmp_path, drift=0.0)
    rules = res["rules"]
    signal_rules = rules[rules["validated"] & rules["rule"].str.contains("ins:|flow:|event:")]
    assert len(signal_rules) <= 2, signal_rules["rule"].tolist()


def test_benjamini_hochberg():
    p = pd.Series([0.001, 0.01, 0.03, 0.5, 0.9])
    assert benjamini_hochberg(p, 0.1).tolist() == [True, True, True, False, False]
