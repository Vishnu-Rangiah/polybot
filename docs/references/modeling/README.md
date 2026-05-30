# Modeling — Reference

The math layer between data and trades: turn a weather forecast into a fair
probability, compare it to a market price, and score how good the predictions were.

| File | Covers |
|---|---|
| `probability-and-scoring.md` | Price↔probability, edge/EV after fees, forecast→bucket probability, Brier / log loss / calibration, the trading metrics (PnL, Sharpe, drawdown), Kelly sizing, and project-specific pitfalls |

Authored for this repo (not scraped) — formulas are standard, examples are tied to
Kalshi weather markets. Grounds the `brier`, fair-value, and edge language used in
`../../DESIGN.md` and the autoresearch backtester (`../autoresearch/README.md`).
