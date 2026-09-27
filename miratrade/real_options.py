"""Re-run the call profiles on **real** option prices instead of modelled ones.

``miratrade massive backfill`` leaves the daily bars of each event's contract in the Massive
cache. This module reads those bars straight off disk (no network, no rate limit), replays the
same target/stop rules ``outcomes.call_outcome`` applies to the modelled premium, and puts the two
answers side by side.

Honest limits, repeated in the report because they decide how much the numbers are worth:

* Massive's free plan holds two years, so only recent events have real prices.
* Only events whose modelled strike and expiry exist as a listed contract are compared; those are
  the more liquid names, which is a selection.
* A bar's close is a *traded* price, not a bid. The same half-spread the model pays is applied on
  both sides, and real spreads on small options are usually wider, so this is still optimistic.
"""
from __future__ import annotations

import json
import re
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from miratrade.config import CACHE_DIR, Config
from miratrade.options_trades import option_contract

OCC_IN_FILENAME = re.compile(r"_O_([A-Z]+)(\d{6})([CP])(\d{8})_")
MAX_ENTRY_GAP_DAYS = 5          # the contract must have traded within a week of the entry


def cached_bars(cache_dir: Path = CACHE_DIR / "massive") -> dict[tuple[str, str, float], pd.DataFrame]:
    """Every option bar series already downloaded, keyed by (underlying, expiry, strike)."""
    out: dict[tuple[str, str, float], pd.DataFrame] = {}
    for path in Path(cache_dir).glob("_v2_aggs_ticker_O_*.json"):
        match = OCC_IN_FILENAME.search(path.name)
        if not match:
            continue
        try:
            results = json.loads(path.read_text(encoding="utf-8")).get("results") or []
        except (OSError, ValueError):
            continue
        if not results:
            continue
        under, yymmdd, kind, strike8 = match.groups()
        if kind != "C":
            continue
        bars = pd.DataFrame(sorted(results, key=lambda r: r["t"]))
        bars["date"] = pd.to_datetime(bars["t"], unit="ms").dt.normalize()
        key = (under, f"20{yymmdd[:2]}-{yymmdd[2:4]}-{yymmdd[4:]}", int(strike8) / 1000)
        keep = bars[["date", "c"]].rename(columns={"c": "close"})
        if key not in out or len(keep) > len(out[key]):
            out[key] = keep
    return out


def real_call_outcome(bars: pd.DataFrame, target: float, stop: float, cfg: Config = Config()) -> tuple[float, float]:
    """Replay one contract's real closes under the same rules as the modelled version: buy at the
    first close plus the half-spread, sell at a close minus it, at most ``call_max_hold`` sessions
    and never inside the last ``call_exit_days_before_expiry`` days."""
    o = cfg.outcomes
    half = cfg.options.half_spread
    closes = bars["close"].to_numpy(dtype=float)
    if len(closes) < 2 or closes[0] <= 0:
        return np.nan, np.nan
    ask = closes[0] * (1 + half)
    last = min(len(closes) - 1, o.call_max_hold)
    ret = 0.0
    for j in range(1, last + 1):
        ret = closes[j] * (1 - half) / ask - 1
        if ret >= target:
            return 1.0, ret
        if ret <= -stop:
            return -1.0, ret
    return 0.0, ret


def compare(report_dir: Path, dte: int = 45, cfg: Config = Config(),
            cache_dir: Path = CACHE_DIR / "massive") -> pd.DataFrame:
    """One row per event that has real prices: the modelled result next to the real one, for every
    target/stop pair of the profiles."""
    events = pd.read_csv(Path(report_dir) / "events.csv", parse_dates=["signal_date", "entry_date"])
    events = events[events["rv20"].notna()]
    bars_by_contract = cached_bars(cache_dir)
    params = replace(cfg.options, target_dte=dte, min_dte=max(21, dte - 15))
    rows = []
    for e in events.to_dict("records"):          # records keep the "event:…" column names readable
        contract = option_contract(e["entry"], e["entry_date"].date(), e["rv20"], params)
        bars = bars_by_contract.get((e["ticker"], str(contract["expiry"]), round(contract["strike"], 3)))
        if bars is None or bars.empty:
            continue
        gap = (bars["date"].iloc[0].date() - e["entry_date"].date()).days
        if not 0 <= gap <= MAX_ENTRY_GAP_DAYS:
            continue
        row = {"ticker": e["ticker"], "entry_date": e["entry_date"], "strike": contract["strike"],
               "expiry": contract["expiry"], "sessions": len(bars),
               "modelled_premium": contract["ask"], "real_premium": float(bars["close"].iloc[0])}
        row["premium_error"] = row["modelled_premium"] / row["real_premium"] - 1
        for target, stop in cfg.outcomes.targets:
            name = f"call{dte}_{int(round(target * 100))}"
            row[f"real_res_{name}"], row[f"real_ret_{name}"] = real_call_outcome(bars, target, stop, cfg)
            row[f"model_res_{name}"] = e.get(f"res_{name}", np.nan)
            row[f"model_ret_{name}"] = e.get(f"ret_{name}", np.nan)
        for flag in ("event:insider_buy", "event:13dg", "event:flow"):
            row[flag] = bool(e.get(flag, False))
        rows.append(row)
    return pd.DataFrame(rows)


def summarise(d: pd.DataFrame, dte: int, cfg: Config = Config()) -> pd.DataFrame:
    """Modelled versus real, profile by profile, on exactly the same events."""
    rows = []
    for target, stop in cfg.outcomes.targets:
        name = f"call{dte}_{int(round(target * 100))}"
        both = d.dropna(subset=[f"real_res_{name}", f"model_res_{name}"])
        if both.empty:
            continue
        for kind in ("model", "real"):
            res, ret = both[f"{kind}_res_{name}"], both[f"{kind}_ret_{name}"]
            rows.append({"perfil": f"+{int(target * 100)} % / −{int(stop * 100)} %",
                         "precios": "modelo" if kind == "model" else "reales", "n": len(both),
                         "objetivo": float((res == 1).mean()), "stop": float((res == -1).mean()),
                         "ninguno": float((res == 0).mean()), "medio": float(ret.mean())})
    return pd.DataFrame(rows)


def report(d: pd.DataFrame, dte: int, cfg: Config = Config()) -> str:
    if d.empty:
        return "# Calls con precios reales\n\nNo hay contratos con precios reales en la caché.\n"
    s = summarise(d, dte, cfg)
    span = f"{d['entry_date'].min():%b %Y} → {d['entry_date'].max():%b %Y}"
    lines = [f"# Calls a {dte} días: precios de modelo frente a precios reales", "",
             f"**{len(d)} eventos** con contrato real en la caché de Massive ({span}). Mismos eventos y mismas "
             "reglas en las dos columnas: se compra al primer cierre y se vende al cierre que toca el objetivo o "
             f"el stop, como máximo {cfg.outcomes.call_max_hold} sesiones.", "",
             "## Qué cambia al usar precios reales", "",
             "| perfil | precios | n | objetivo | stop | ninguno | resultado medio |", "|---|---|---|---|---|---|---|"]
    for r in s.itertuples():
        lines.append(f"| {r.perfil} | {r.precios} | {r.n} | {r.objetivo * 100:.0f} % | {r.stop * 100:.0f} % | "
                     f"{r.ninguno * 100:.0f} % | {r.medio * 100:+.1f} %".replace("-", "−") + " |")
    err = d["premium_error"]
    lines += ["", "## Cuánto se equivoca el modelo al poner el precio de entrada", "",
              f"- Error medio **{err.mean() * 100:+.1f} %**, mediano {err.median() * 100:+.1f} % "
              "(positivo = el modelo cobra de más).",
              f"- Fuera de ±50 % en el **{(err.abs() > 0.5).mean() * 100:.0f} %** de los eventos "
              f"(percentil 10: {err.quantile(0.1) * 100:+.0f} %, percentil 90: {err.quantile(0.9) * 100:+.0f} %).",
              "", "## Lo que estos números no dicen", "",
              "- El plan gratuito de Massive guarda dos años: esto no cubre los cinco del análisis.",
              "- Solo entran los eventos cuyo contrato modelado existe de verdad y se negoció; "
              "suelen ser las empresas más líquidas, así que la muestra está elegida.",
              "- El cierre de una opción es un precio negociado, no la demanda. Se aplica el mismo medio "
              f"spread del modelo ({cfg.options.half_spread * 100:.1f} %) a la entrada y a la salida, y en "
              "opciones poco líquidas el spread real es mayor: estas cifras siguen siendo optimistas.",
              ""]
    return "\n".join(lines).replace("−-", "−")
