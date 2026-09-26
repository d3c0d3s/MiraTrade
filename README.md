# MiraTrade

MiraTrade tests whether **insider buying** and **unusual options activity** improve **swing trades**. It
backtests every candidate trade over a recent window, usually the last 90 days, and mines which
combinations of conditions separated winners from losers. A rule counts as an edge only if it
holds up **out of sample**.

## Quick start

```bash
pip install -e ".[yf,dev]"
miratrade demo                               # offline: synthetic market with a planted edge
miratrade analyze --days 90                  # live: SEC Form 4 + prices, last 90 days
miratrade analyze --days 90 --flow flow.csv  # add an options-flow export
miratrade snapshot AAPL NVDA TSLA            # save today's CBOE chains (run daily to build flow history)
```

Output goes to `reports/`: `edge_report.md`, `trades.csv`, `rules.csv` (every rule tested) and
`rules_options.csv` (the same rules measured on calls) and `candidates.csv` (tickers whose latest
bar matches a validated rule, with entry, stop, target and a suggested call) and `walk_forward.csv`
(one row per walk-forward fold).

## Pipeline

| Stage | Module | What it does |
|---|---|---|
| Insiders | `data/sec.py` | SEC quarterly insider data sets (bulk) + EDGAR daily index / Form 4 XML for the current quarter. Open-market buys (`P`) and sells (`S`) only. |
| 13D / 13G | `data/ownership.py` | Beneficial-ownership filings (someone crossed 5%) from EDGAR's quarterly full index. The subject is the party with a ticker (SEC ticker list + issuers seen in insider filings, so delisted names still map); a filing's header breaks ties. Index-fund 13Gs (Vanguard, BlackRock, State Street) are flagged passive and ignored. |
| Short volume | `data/finra.py` | FINRA Reg SHO daily short-sale volume, free, published the evening of each session. |
| Options flow | `data/options.py` | Vendor CSV import (Unusual Whales, Barchart, and similar; columns auto-mapped) or daily CBOE delayed chains. |
| Prices | `data/prices.py` | yfinance, falling back to Stooq; cached. |
| Signals | `signals/` | Insider features: buy value, number of distinct buyers, clusters (2+ insiders within 10 days), CEO/CFO buys, stake increase, heavy selling. Unusual flow: premium ≥ $100k, volume/OI ≥ 1.5, ≤ 60 DTE, ≤ 15% OTM, direction from aggressor side. Setups: 20-day breakout on volume, pullback to the 20-day average in an uptrend, RSI oversold bounce. Smart money: a 13D or non-index 13G in the last 30 days (a new one is also an entry event), short-volume ratio unusually low or high against the ticker's own last 20 sessions (\|z\| ≥ 1). Skip with `--no-smart-money`. |
| Backtest | `backtest.py` | Signal at close, entry at the next open, 1.5×ATR stop, 3×ATR target (2R), 15-bar time stop. When stop and target are both touched on the same bar, it assumes the stop. A gap fills at the open. One trade per ticker at a time. |
| Options | `options_trades.py` | The same signal traded as a ~0.65-delta call on the monthly expiry nearest 45 days out (at least 30), with the same entry and exit dates. Priced with Black-Scholes (realised vol × 1.15, 2.5% half-spread each side). Rules are mined separately for calls, and candidates include a suggested contract. |
| Edge | `edge.py` | Every conjunction of up to 3 conditions is tested on the first 60% of the window and validated on the last 40%. Significance is lift over the baseline, with a Benjamini-Hochberg correction for multiple testing. |
| Walk-forward | `edge.py` | The same discovery step re-run on an expanding window: 3 folds over the last 60% of trades, each mining only on trades that had *exited* before the fold starts. Reports each fold, each rule's out-of-sample record (`wf_*` columns, `wf_confirmed`) and all picked trades pooled as lift over the baseline. |
| Regimes | `regimes.py` | Point-in-time market type on each signal date: bull / sideways / bear (SPY and its 50-day vs the 200-day average) and high / low volatility (SPY 20-day realised vol vs its one-year median). Baseline and validated rules are broken down by regime. |
| Survivorship | `survivorship.py` | Tickers whose data ends early count as delisted: trades still open are closed at the last bar (optional haircut) and kept, not dropped. Reports tickers with no or too-short price data and the insider buys and option prints lost with them. |

Every threshold is in `miratrade/config.py`.

## Guardrails against fooling yourself

- **Point-in-time data:** insider signals become visible on the SEC **filing date**, not the trade date.
- **No look-ahead:** entries fill at the next session's open.
- **Multiple testing:** trying about 100 rules will turn up some "winners" by chance. The BH
  correction plus a separate validation period filter them out. The test suite checks that a
  pure-noise market yields no validated signal rules, and that a planted insider/flow edge is recovered.
- **Option prices are modelled, not quoted.** Use the comparison to decide between shares and calls,
  and check the live chain (open interest, spread, earnings date) before buying.
- **Walk-forward:** a single split can get lucky. Walk-forward re-runs discovery several times and
  only scores rules on trades that came after them. With 90 days each fold holds ~35 trades and
  usually picks nothing; run `--days 365` or more to make it meaningful. The tests check that
  ~1.5 years of synthetic data recovers the planted edge and that pure noise yields nothing.
- **Market regime:** check the regime table before generalising. A rule seen only in a bear or
  high-vol market is a hypothesis for that market only.
- **Survivorship:** free price sources drop most delisted tickers. The coverage section reports how
  many tickers and signals were lost. Set `SurvivorshipParams.delist_exit_haircut` (e.g. 0.3) to
  stress-test delisted exits.
- **Limits:** Paper-trade validated rules before sizing up. Costs and slippage are not modelled.

## Data notes

- SEC requires a contact User-Agent: `export MIRATRADE_SEC_UA="Your Name you@example.com"`.
- The first run over the current quarter downloads each Form 4 (about 1,000 a day at 8 requests
  per second), so it takes a while. Everything is cached in `.cache/`.
- Free *historical* options flow doesn't exist. Either export 90 days from a flow vendor and pass
  `--flow`, or run `miratrade snapshot` daily to build your own history.

## Claude Code agents

`.claude/agents/` holds 12 specialised subagents that Claude Code uses on this project:

| Agent | Role |
|---|---|
| `investigador-cuantitativo` | Signals, rule mining, walk-forward and statistical validation |
| `auditor-backtests` | Read-only review for look-ahead, survivorship, overfitting and cost bias |
| `especialista-opciones` | Option pricing, greeks, strike/expiry selection, liquidity |
| `ingeniero-datos` | SEC, price, option and vendor data sources; caching and data quality |
| `integrador-brokers` | Schwab / TradeStation / E*TRADE APIs, OAuth, orders, simulated broker |
| `gestor-riesgo` | Position sizing, limits, automatic mode and kill-switch review |
| `desarrollador-escritorio` | PySide6 + Lightweight Charts Windows app, PyInstaller |
| `disenador-ux` | Mockups, visual consistency, accessibility, flows |
| `qa-tester` | Tests (pytest, pytest-qt), bug reproduction |
| `devops-releases` | GitHub Actions, Windows builds, releases |
| `auditor-seguridad` | Credentials, tokens, secrets, dependencies, order safety |
| `tutor-trading` | Explains reports and concepts to the user in plain Spanish |

To use them in every project on your own machine, copy them to `~/.claude/agents/`.
