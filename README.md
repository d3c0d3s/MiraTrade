# MiraBot

MiraBot tests whether **insider buying** and **unusual options activity** improve **swing trades**. It
backtests every candidate trade over a recent window, usually the last 90 days, and mines which
combinations of conditions separated winners from losers. A rule counts as an edge only if it
holds up **out of sample**.

## Quick start

```bash
pip install -e ".[yf,dev]"
mirabot demo                               # offline: synthetic market with a planted edge
mirabot analyze --days 90                  # live: SEC Form 4 + prices, last 90 days
mirabot analyze --days 90 --flow flow.csv  # add an options-flow export
mirabot snapshot AAPL NVDA TSLA            # save today's CBOE chains (run daily to build flow history)
```

Output goes to `reports/`: `edge_report.md`, `trades.csv`, `rules.csv` (every rule tested) and
`rules_options.csv` (the same rules measured on calls) and `candidates.csv` (tickers whose latest
bar matches a validated rule, with entry, stop, target and a suggested call).

## Pipeline

| Stage | Module | What it does |
|---|---|---|
| Insiders | `data/sec.py` | SEC quarterly insider data sets (bulk) + EDGAR daily index / Form 4 XML for the current quarter. Open-market buys (`P`) and sells (`S`) only. |
| Options flow | `data/options.py` | Vendor CSV import (Unusual Whales, Barchart, and similar; columns auto-mapped) or daily CBOE delayed chains. |
| Prices | `data/prices.py` | yfinance, falling back to Stooq; cached. |
| Signals | `signals/` | Insider features: buy value, number of distinct buyers, clusters (2+ insiders within 10 days), CEO/CFO buys, stake increase, heavy selling. Unusual flow: premium ≥ $100k, volume/OI ≥ 1.5, ≤ 60 DTE, ≤ 15% OTM, direction from aggressor side. Setups: 20-day breakout on volume, pullback to the 20-day average in an uptrend, RSI oversold bounce. |
| Backtest | `backtest.py` | Signal at close, entry at the next open, 1.5×ATR stop, 3×ATR target (2R), 15-bar time stop. When stop and target are both touched on the same bar, it assumes the stop. A gap fills at the open. One trade per ticker at a time. |
| Options | `options_trades.py` | The same signal traded as a ~0.65-delta call on the monthly expiry nearest 45 days out (at least 30), with the same entry and exit dates. Priced with Black-Scholes (realised vol × 1.15, 2.5% half-spread each side). Rules are mined separately for calls, and candidates include a suggested contract. |
| Edge | `edge.py` | Every conjunction of up to 3 conditions is tested on the first 60% of the window and validated on the last 40%. Significance is lift over the baseline, with a Benjamini-Hochberg correction for multiple testing. |

Every threshold is in `mirabot/config.py`.

## Guardrails against fooling yourself

- **Point-in-time data:** insider signals become visible on the SEC **filing date**, not the trade date.
- **No look-ahead:** entries fill at the next session's open.
- **Multiple testing:** trying about 100 rules will turn up some "winners" by chance. The BH
  correction plus a separate validation period filter them out. The test suite checks that a
  pure-noise market yields no validated signal rules, and that a planted insider/flow edge is recovered.
- **Option prices are modelled, not quoted.** Use the comparison to decide between shares and calls,
  and check the live chain (open interest, spread, earnings date) before buying.
- **Limits:** 90 days is one market regime. Paper-trade validated rules before sizing up. Costs and
  slippage are not modelled.

## Data notes

- SEC requires a contact User-Agent: `export MIRABOT_SEC_UA="Your Name you@example.com"`.
- The first run over the current quarter downloads each Form 4 (about 1,000 a day at 8 requests
  per second), so it takes a while. Everything is cached in `.cache/`.
- Free *historical* options flow doesn't exist. Either export 90 days from a flow vendor and pass
  `--flow`, or run `mirabot snapshot` daily to build your own history.
