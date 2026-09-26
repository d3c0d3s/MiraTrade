"""Stock-driven experiments: the event is read on the stock; the call is only the vehicle.

Every event (same trigger and 20-session cooldown as ``outcomes.py``) is entered at the next
session's open with each instrument, the shares or a call picked by delta on the monthly expiry at
least ``dte`` days out, and closed by one exit rule:

* a **stop on the stock** checked first every day: none, −10 %, 2×ATR or 3×ATR below the entry
  (a gap through it fills at the open);
* ``premium40_25``: the current profile, +40 % / −25 % on the premium at the close (reference);
* ``fixed30``: take +30 % at the close;
* ``run30_*``: once the position closes at +30 % or more, let it run and sell at the next open
  after a technical exit (close under the 10-session average, a 2×ATR chandelier from the highest
  close, or the MACD histogram turning negative) or a fall back to +20 %;
* always: at most ``max_hold`` sessions and never within two weeks of expiry.

Call prices are **modelled** (Black-Scholes, realised volatility × ``iv_mult``, half-spread paid
both ways), not quotes. The first 60 % of the window chooses; the rest confirms.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from miratrade.backtest import conditions, entry_trigger
from miratrade.config import Config
from miratrade.options_trades import bs_price, option_contract
from miratrade.outcomes import EVENT_TYPES

_ERF = np.frompyfunc(math.erf, 1, 1)


def norm_cdf(x) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    return 0.5 * (1.0 + _ERF(x / math.sqrt(2.0)).astype(float))


def bs_call(s, k: float, t, r: float, sigma: float) -> np.ndarray:
    """Vectorised Black-Scholes call; intrinsic value once ``t`` reaches 0."""
    s, t = np.broadcast_arrays(np.asarray(s, dtype=float), np.asarray(t, dtype=float))
    shape = s.shape
    s, t = s.reshape(-1), np.maximum(t.reshape(-1), 0.0)
    out = np.maximum(s - k, 0.0)
    live = t > 0
    if live.any():
        st = sigma * np.sqrt(t[live])
        d1 = (np.log(s[live] / k) + (r + 0.5 * sigma ** 2) * t[live]) / st
        out[live] = s[live] * norm_cdf(d1) - k * np.exp(-r * t[live]) * norm_cdf(d1 - st)
    return out.reshape(shape)


# --------------------------------------------------------------------------- events

def technicals(ind: pd.DataFrame) -> dict[str, np.ndarray]:
    c = ind["close"]
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    return {"sma10": c.rolling(10).mean().to_numpy(), "macd_hist": (macd - macd.ewm(span=9, adjust=False).mean()).to_numpy(),
            "atr": ind["atr"].to_numpy()}


def extract_events(panel: dict[str, pd.DataFrame], cfg: Config = Config(), start: pd.Timestamp | None = None,
                   insiders: pd.DataFrame | None = None, issuer_kind: dict[str, str] | None = None) -> pd.DataFrame:
    """One row per event with what the filters need: its types, whether every fresh insider buy
    was under a 10b5-1 plan, and the issuer kind (company / fund / spac)."""
    issuer_kind = issuer_kind or {}
    buys = None
    if insiders is not None and len(insiders):
        b = insiders[(insiders["code"] == "P") & (insiders["value"] >= cfg.insider.min_value_usd)]
        buys = b.assign(fd=pd.to_datetime(b["filing_date"]).dt.normalize(),
                        plan=b["plan_10b5_1"].astype(bool) if "plan_10b5_1" in b else False)
    rows = []
    for t, ind in panel.items():
        fired = np.flatnonzero(entry_trigger(ind).to_numpy())
        opens, closes = ind["open"].to_numpy(), ind["close"].to_numpy()
        cool = -1
        tb = buys[buys["ticker"] == t] if buys is not None else None
        for s in fired:
            if s <= cool or (start is not None and ind.index[s] < start):
                continue
            i = s + 1
            if i >= len(ind) or closes[s] < cfg.trade.min_price:
                continue
            cool = s + cfg.outcomes.event_cooldown
            row = ind.iloc[s]
            cond = conditions(row)
            plan_only = False
            if cond["event:insider_buy"] and tb is not None and len(tb):
                prev = ind.index[s - 1] if s > 0 else pd.Timestamp.min
                fresh = tb[(tb["fd"] > prev) & (tb["fd"] <= ind.index[s])]
                plan_only = bool(len(fresh)) and bool(fresh["plan"].all())
            rows.append({"ticker": t, "s": s, "signal_date": ind.index[s], "entry_date": ind.index[i],
                         "entry": float(opens[i]), "rv20": float(row.get("rv20", np.nan)), "atr": float(row["atr"]),
                         "mkt_trend": row.get("mkt_trend", "unknown"), **{k: bool(cond[k]) for k in EVENT_TYPES},
                         "mkt_cap": float(row.get("mkt_cap", np.nan)),
                         "buy_pct_cap": float(row["ins_buy_value"] / row["mkt_cap"])
                         if np.isfinite(row.get("mkt_cap", np.nan)) and row.get("mkt_cap", 0) > 0 else np.nan,
                         "plan_only": plan_only, "issuer_kind": issuer_kind.get(t, "company")})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- one trade

@dataclass(frozen=True)
class Instrument:
    kind: str                            # "stock" or "call"
    delta: float = 0.0
    dte: int = 0

    @property
    def name(self) -> str:
        return "acción" if self.kind == "stock" else f"call Δ{self.delta:.2f} {self.dte}d"


def instruments(cfg: Config) -> list[Instrument]:
    e = cfg.experiment
    return [Instrument("stock")] + [Instrument("call", d, dte) for dte in e.dtes for d in e.deltas]


def stop_price(kind: str, entry: float, atr: float) -> float | None:
    if kind == "none":
        return None
    if kind == "pct10":
        return entry * 0.90
    k = {"atr2": 2.0, "atr3": 3.0}[kind]
    level = entry - k * atr
    return level if np.isfinite(level) and level > 0 else None


class Position:
    """Value of one instrument bought at the entry open: close path and value at any price."""

    def __init__(self, inst: Instrument, ind: pd.DataFrame, i: int, ev_vol: float, cfg: Config):
        self.inst = inst
        self.i = i
        self.dates = ind.index
        entry = float(ind["open"].iat[i])
        e = cfg.experiment
        if inst.kind == "stock":
            self.cost, self.last = entry, i + e.max_hold
            self.contract = None
        else:
            p = replace(cfg.options, target_delta=inst.delta, target_dte=inst.dte, min_dte=inst.dte)
            c = option_contract(entry, self.dates[i].date(), ev_vol, p)
            self.contract, self.p = c, p
            self.cost = c["ask"]
            last_day = pd.Timestamp(c["expiry"]) - pd.Timedelta(days=e.exit_days_before_expiry)
            by_expiry = int(self.dates.searchsorted(last_day, side="right")) - 1
            self.last = min(i + e.max_hold, by_expiry) if by_expiry < len(self.dates) - 1 else i + e.max_hold
        self.ok = np.isfinite(self.cost) and self.cost > 0 and self.last < len(self.dates) and self.last > i

    def value(self, price, j) -> np.ndarray | float:
        if self.contract is None:
            return price
        c = self.contract
        t = (pd.Timestamp(c["expiry"]) - self.dates[j]).days / 365 if np.isscalar(j) else \
            (pd.Timestamp(c["expiry"]) - self.dates[j]).days.to_numpy() / 365
        return bs_call(price, c["strike"], t, self.p.rate, c["sigma"]) * (1 - self.p.half_spread)

    def close_returns(self, closes: np.ndarray) -> np.ndarray:
        j = np.arange(self.i, self.last + 1)
        return np.asarray(self.value(closes[j], j), dtype=float) / self.cost - 1


def run_exit(pos: Position, arr: dict[str, np.ndarray], tech: dict[str, np.ndarray], rets: np.ndarray,
             stop: float | None, rule: str, cfg: Config) -> dict:
    """Walk the trade day by day; returns ret, days, reason, whether +30 % was reached, best close."""
    e = cfg.experiment
    o, l, c = arr["open"], arr["low"], arr["close"]
    i, last = pos.i, pos.last

    def done(price, j, reason, at_close_ret=None):
        r = at_close_ret if at_close_ret is not None else float(pos.value(price, j)) / pos.cost - 1
        best = float(rets[: j - i + 1].max())
        return {"ret": r, "days": j - i, "reason": reason, "reached30": best >= e.activation, "best": best}

    active, peak, pending = False, -np.inf, None
    for j in range(i, last + 1):
        if pending:
            return done(o[j], j, pending)
        if stop is not None:
            if j > i and o[j] <= stop:
                return done(o[j], j, "stop")
            if l[j] <= stop:
                return done(stop, j, "stop")
        r = rets[j - i]
        if rule == "premium40_25":
            if r >= 0.40:
                return done(c[j], j, "objetivo", r)
            if r <= -0.25:
                return done(c[j], j, "stop prima", r)
        elif rule == "fixed30":
            if r >= e.activation:
                return done(c[j], j, "objetivo", r)
        else:
            if not active and r >= e.activation:
                active, peak = True, c[j]
            if active:
                peak = max(peak, c[j])
                if r <= e.floor:
                    pending = "suelo +20 %"
                elif rule == "run30_sma10" and c[j] < tech["sma10"][j]:
                    pending = "bajo media 10"
                elif rule == "run30_chandelier" and c[j] < peak - e.chandelier_atr * tech["atr"][j]:
                    pending = "chandelier"
                elif rule == "run30_macd" and tech["macd_hist"][j] < 0:
                    pending = "MACD"
                if pending and j == last:
                    return done(c[j], j, pending, r)
        if j == last:
            return done(c[j], j, "tiempo", r)
    return done(c[last], last, "tiempo", rets[-1])


# --------------------------------------------------------------------------- the grid

def run_grid(panel: dict[str, pd.DataFrame], events: pd.DataFrame, cfg: Config = Config()) -> pd.DataFrame:
    """One row per (event, instrument, stop, exit) that could be completed with the data."""
    e = cfg.experiment
    out = []
    insts = instruments(cfg)
    for ticker, evs in events.groupby("ticker"):
        ind = panel[ticker]
        arr = {k: ind[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close")}
        tech = technicals(ind)
        for ev in evs.itertuples():
            i = ev.s + 1
            for inst in insts:
                if inst.kind == "call" and not np.isfinite(ev.rv20):
                    continue
                pos = Position(inst, ind, i, ev.rv20, cfg)
                if not pos.ok:
                    continue
                rets = pos.close_returns(arr["close"])
                for stop_kind in e.stops:
                    stop = stop_price(stop_kind, float(arr["open"][i]), ev.atr)
                    if stop_kind != "none" and stop is None:
                        continue
                    for rule in e.exits:
                        if rule == "premium40_25" and inst.kind == "stock":
                            continue
                        res = run_exit(pos, arr, tech, rets, stop, rule, cfg)
                        out.append((ev.Index, inst.name, stop_kind, rule, res["ret"], res["days"], res["reason"],
                                    res["reached30"], res["best"]))
    trades = pd.DataFrame(out, columns=["event", "instrument", "stop", "exit", "ret", "days", "reason",
                                        "reached30", "best"])
    cols = ["ticker", "signal_date", "mkt_trend", *EVENT_TYPES, "plan_only", "issuer_kind", "mkt_cap", "buy_pct_cap"]
    return trades.join(events[[c for c in cols if c in events]], on="event")


def stats(r: pd.Series, reached: pd.Series | None = None, days: pd.Series | None = None) -> dict:
    r = r.dropna()
    n = len(r)
    if n == 0:
        return {"n": 0}
    gains, losses = r[r > 0].sum(), -r[r < 0].sum()
    sd = r.std(ddof=1) if n > 1 else np.nan
    return {"n": n, "media": r.mean(), "mediana": r.median(), "acierto": (r > 0).mean(),
            "pf": gains / losses if losses > 0 else np.inf, "t": r.mean() / (sd / math.sqrt(n)) if sd and sd > 0 else np.nan,
            "llega30": reached.mean() if reached is not None else np.nan,
            "dias": days.mean() if days is not None else np.nan}


def summarize(trades: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    rows = []
    for key, g in trades.groupby(by, sort=False):
        key = key if isinstance(key, tuple) else (key,)
        rows.append({**dict(zip(by, key)), **stats(g["ret"], g["reached30"], g["days"])})
    return pd.DataFrame(rows)


def split_date(events: pd.DataFrame, cfg: Config = Config()) -> pd.Timestamp:
    d = events["signal_date"]
    return d.min() + (d.max() - d.min()) * cfg.experiment.train_fraction


def clean(trades: pd.DataFrame) -> pd.DataFrame:
    """The pre-registered event filter: operating companies only, and not insider buys that were
    all under a 10b5-1 plan."""
    return trades[(trades["issuer_kind"] == "company") & ~trades["plan_only"]]


# --------------------------------------------------------------------------- report

DEFAULT_RULE = ("call Δ0.65 60d", "atr2", "run30_chandelier")   # the user's rule, pre-registered
CURRENT = ("call Δ0.65 45d", "none", "premium40_25")            # today's call profile
EXIT_LABELS = {"premium40_25": "prima +40/−25", "fixed30": "fijo +30 %", "run30_sma10": "+30 % y media 10",
               "run30_chandelier": "+30 % y chandelier", "run30_macd": "+30 % y MACD"}
STOP_LABELS = {"none": "sin stop", "pct10": "−10 %", "atr2": "2×ATR", "atr3": "3×ATR"}
HEAD = "| | n | media | mediana | acierto | PF | t | llega a +30 % |"
SEP = "|---|---|---|---|---|---|---|---|"


def _pct(x, signed: bool = True) -> str:
    if x is None or not np.isfinite(x):
        return "–"
    return f"{x * 100:+.1f} %" if signed else f"{x * 100:.0f} %"


def _row(label: str, s: dict, extra: str = "") -> str:
    if not s or s.get("n", 0) == 0:
        return f"| {label} | 0 | – | – | – | – | – | – |{extra}"
    pf = "∞" if not np.isfinite(s["pf"]) else f"{s['pf']:.2f}"
    t = f"{s['t']:.1f}" if np.isfinite(s["t"]) else "–"
    return (f"| {label} | {s['n']} | {_pct(s['media'])} | {_pct(s['mediana'])} | {_pct(s['acierto'], False)} | "
            f"{pf} | {t} | {_pct(s['llega30'], False)} |{extra}")


def _label(key: tuple) -> str:
    return f"{key[0]}, stop {STOP_LABELS[key[1]]}, salida {EXIT_LABELS[key[2]]}"


def _cfg(trades: pd.DataFrame, key: tuple) -> pd.DataFrame:
    inst, stop, ex = key
    return trades[(trades["instrument"] == inst) & (trades["stop"] == stop) & (trades["exit"] == ex)]


def _s(df: pd.DataFrame) -> dict:
    return stats(df["ret"], df["reached30"], df["days"])


def report(trades: pd.DataFrame, events: pd.DataFrame, cfg: Config, meta: dict) -> tuple[str, pd.DataFrame]:
    """Markdown report plus the summary of every configuration on clean events (train / test)."""
    e = cfg.experiment
    cut = split_date(events, cfg)
    trades = trades.assign(period=np.where(trades["signal_date"] < cut, "train", "test"))
    cl = clean(trades)
    is_clean = (events["issuer_kind"] == "company") & ~events["plan_only"]
    lines = [
        "# Experimentos: la acción decide, la call es el vehículo", "",
        f"Ventana **{meta['start']} → {meta['end']}** · {len(events)} eventos · se elige con los eventos anteriores "
        f"al **{cut:%Y-%m-%d}** (train) y se confirma con los posteriores (test).", "",
        "Entrada a la apertura siguiente al evento. Precios de las calls **de modelo** (Black-Scholes con volatilidad "
        f"realizada × {cfg.options.iv_mult}, medio spread de {cfg.options.half_spread * 100:.1f} % en cada lado), no "
        f"cotizaciones. Máximo {e.max_hold} sesiones y nunca en las dos últimas semanas antes del vencimiento. "
        "Los resultados son % sobre lo invertido en cada operación (la prima en las calls).", "",
        "## Eventos", "", "| | eventos |", "|---|---|", f"| Todos | {len(events)} |",
        *(f"| {lab} | {int(events[k].sum())} |" for k, lab in
          (("event:insider_buy", "Compras de directivos"), ("event:13dg", "13D / 13G"),
           ("event:flow", "Opciones inusuales"))),
        f"| Emisor fondo / ETF / BDC | {int((events['issuer_kind'] == 'fund').sum())} |",
        f"| Emisor SPAC | {int((events['issuer_kind'] == 'spac').sum())} |",
        f"| Compras solo con plan 10b5-1 | {int(events['plan_only'].sum())} |",
        f"| **Limpios** (empresas, sin 10b5-1) | {int(is_clean.sum())} |", "",
        "## Prueba 1 · Calidad del evento", "",
    ]
    for title, key in (("Tu regla: " + _label(DEFAULT_RULE), DEFAULT_RULE),
                       ("Perfil actual: " + _label(CURRENT), CURRENT)):
        t = _cfg(trades, key)
        ct = clean(t)
        sets = [("Todos", t), ("Sin fondos ni SPAC", t[t["issuer_kind"] == "company"]),
                ("Sin compras con plan 10b5-1", t[~t["plan_only"]]), ("**Limpios**", ct),
                ("Solo fondos / ETF / BDC", t[t["issuer_kind"] == "fund"])]
        sets += [(f"Limpios · {lab}", ct[ct[k]]) for k, lab in
                 (("event:insider_buy", "directivos"), ("event:13dg", "13D / 13G"), ("event:flow", "opciones"))]
        if "mkt_cap" in ct:
            cap = ct["mkt_cap"]
            sets += [("Limpios · capitalización < 300 M$", ct[cap < 3e8]),
                     ("Limpios · 300 M$ – 2.000 M$", ct[(cap >= 3e8) & (cap < 2e9)]),
                     ("Limpios · 2.000 – 10.000 M$", ct[(cap >= 2e9) & (cap < 1e10)]),
                     ("Limpios · > 10.000 M$", ct[cap >= 1e10]),
                     ("Limpios · sin dato de capitalización", ct[cap.isna()]),
                     ("Limpios · compra ≥ 0,1 % de la capitalización", ct[ct["buy_pct_cap"] >= 0.001]),
                     ("Limpios · compra < 0,1 % de la capitalización", ct[ct["buy_pct_cap"] < 0.001])]
        lines += [f"**{title}** (periodo completo; última columna: media en test)", "",
                  HEAD + " media test |", SEP + "---|"]
        lines += [_row(lab, _s(g), f" {_pct(_s(g[g['period'] == 'test']).get('media', np.nan))} |") for lab, g in sets]
        lines.append("")

    lines += ["## Prueba 2 · Instrumento (eventos limpios)", "",
              f"Misma entrada y misma salida para todos: stop {STOP_LABELS[DEFAULT_RULE[1]]} en la acción y "
              f"{EXIT_LABELS[DEFAULT_RULE[2]]}.", "",
              "| instrumento | n train | media train | n test | media test | acierto test | PF test | llega +30 % test |",
              "|---|---|---|---|---|---|---|---|"]
    for inst in [i.name for i in instruments(cfg)]:
        g = _cfg(cl, (inst, DEFAULT_RULE[1], DEFAULT_RULE[2]))
        tr, te = _s(g[g["period"] == "train"]), _s(g[g["period"] == "test"])
        if te.get("n", 0) == 0:
            continue
        pf = "∞" if not np.isfinite(te["pf"]) else f"{te['pf']:.2f}"
        lines.append(f"| {inst} | {tr.get('n', 0)} | {_pct(tr.get('media', np.nan))} | {te['n']} | {_pct(te['media'])} | "
                     f"{_pct(te['acierto'], False)} | {pf} | {_pct(te['llega30'], False)} |")

    lines += ["", "## Prueba 3 · Stop en la acción y salida (eventos limpios)", ""]
    for inst in ("acción", DEFAULT_RULE[0]):
        lines += [f"**{inst}** · media train / media test", "",
                  "| salida | " + " | ".join(STOP_LABELS[s] for s in e.stops) + " |", "|---|" + "---|" * len(e.stops)]
        for ex in e.exits:
            if ex == "premium40_25" and inst == "acción":
                continue
            cells = []
            for st in e.stops:
                g = _cfg(cl, (inst, st, ex))
                a, b = _s(g[g["period"] == "train"]), _s(g[g["period"] == "test"])
                cells.append(f"{_pct(a.get('media', np.nan))} / {_pct(b.get('media', np.nan))}" if a.get("n") else "–")
            lines.append(f"| {EXIT_LABELS[ex]} | " + " | ".join(cells) + " |")
        lines.append("")

    summ = summarize(cl, ["instrument", "stop", "exit", "period"])
    wide = summ.pivot_table(index=["instrument", "stop", "exit"], columns="period",
                            values=["n", "media", "acierto", "pf", "t", "llega30"])
    wide.columns = [f"{a}_{b}" for a, b in wide.columns]
    wide = wide.reset_index()
    ranked = wide[wide["n_train"] >= e.min_n].sort_values("media_train", ascending=False)
    lines += ["## Las 10 mejores configuraciones en train, y lo que hicieron en test", "",
              f"Se probaron {len(wide)} configuraciones: la mejor en train suele empeorar en test por azar. "
              "Una configuración solo cuenta si **también** gana en test.", "",
              "| instrumento | stop | salida | n train | media train | n test | media test | acierto test | t test |",
              "|---|---|---|---|---|---|---|---|---|"]
    for r in ranked.head(10).itertuples():
        n_test = int(r.n_test) if np.isfinite(r.n_test) else 0
        t_test = f"{r.t_test:.1f}" if np.isfinite(r.t_test) else "–"
        lines.append(f"| {r.instrument} | {STOP_LABELS[r.stop]} | {EXIT_LABELS[r.exit]} | {int(r.n_train)} | "
                     f"{_pct(r.media_train)} | {n_test} | {_pct(r.media_test)} | {_pct(r.acierto_test, False)} | {t_test} |")
    both = wide[(wide["media_train"] > 0) & (wide["media_test"] > 0) & (wide["n_train"] >= e.min_n)]
    lines += ["", f"Configuraciones con media positiva en train **y** en test: **{len(both)}** de {len(wide)}.", ""]

    if len(ranked):
        b = ranked.iloc[0]
        lines += ["## Por régimen de mercado (limpios, periodo completo)", "", HEAD, SEP]
        for lab, k in (("Tu regla", DEFAULT_RULE), ("Mejor en train", (b["instrument"], b["stop"], b["exit"]))):
            for reg, gg in _cfg(cl, k).groupby("mkt_trend"):
                lines.append(_row(f"{lab} · mercado {reg}", _s(gg)))
        lines.append("")
    return "\n".join(lines), wide
