# Findings: Do Simple Technical Signals Have Edge on Liquid Crypto?

**Author's note:** This documents a research project spanning nine sessions
of iterative development and testing. The honest conclusion is at the bottom.
Read the whole thing if you want the methodology; skip to "Final Verdict"
if you just want the answer.

---

## The Hypothesis

Crypto markets are less efficient than traditional finance — 24/7 trading,
retail dominance, small-cap altcoins with thin liquidity. If any public
technical signal has edge, it should show up on liquid crypto pairs.

**Signals tested:**

1. **RSI/EMA trend following** — buy pullbacks in uptrends
2. **Mean reversion** — buy oversold dips, exit at mean
3. **Breakout** — buy N-bar highs with volume confirmation

---

## The Methodology

**Data:** 5 liquid pairs (SOL, BTC, ETH, BNB, XRP) via Binance. Four
timeframes (5m, 15m, 1h, 4h). Up to 180 days of history for slower
timeframes.

**Fees:** 0.26% taker applied on both entry and exit. This is the single
most important detail — most retail backtests ignore or underestimate fees.

**Metrics tracked:**

- `strategy_return` — PnL from completed trades only (the honest edge)
- `equity_return` — total portfolio return including market drift
- Win rate, R:R ratio, max drawdown, exit reason breakdown

**Validation:**

- **In-sample** (Apr–Sep 2026) — used for parameter tuning
- **Out-of-sample** (Oct 2025–Mar 2026) — used only for final validation

---

## Test 1: RSI/EMA Trend Following

**Setup:** EMA(8) > EMA(21), RSI between 47–53, enter long. Exit on TP
(3×ATR), SL (1.4×ATR), RSI extreme, or 18-bar timeout.

**5m results (30 days):**

- 136 trades
- Win rate: 32.4%
- **Strategy return: -17.81%**
- TP exits: 11 | SL exits: 60

**1h results (90 days):**

- 29 trades
- Win rate: 34.5%
- **Strategy return: -7.27%**
- **TP exits: 0** (all trades exited via SL/RSI/TIME)

**Interpretation:** The signal doesn't work at any timeframe. On 5m, fees
destroy it. On 1h, the 3×ATR target is never reached.

### Grid Search (1,296 combinations on 5m)

Best result: **-8.20%** (still losing). Median across all combos: -4.63%.
**No parameter combination produced a positive result.**

---

## Test 2: Mean Reversion

**Setup:** Buy when price < EMA(20) - 2σ AND RSI < 30. Exit at EMA(20),
RSI > 55, or 12-bar timeout.

**5m results (30 days):**

- 66 trades
- Win rate: 42.4%
- **Strategy return: -8.14%**
- Better than RSI/EMA, but still negative

**1h results (90 days):**

- 14 trades
- **Strategy return: -1.27%**
- Too few trades for statistical significance

### Grid Search (768 combinations)

Best result: **+8.01%** — but from only **7 trades**. Statistically
meaningless.

### Split-Sample Test

Broke the top combo's performance in half:

- In-sample: 2 trades
- Out-of-sample: 5 trades

**7 trades total.** Cannot validate a strategy on 7 trades.

**Interpretation:** The signal fires too rarely to trade, and when it fires
its accuracy is a coin flip.

---

## Test 3: Breakout

**Setup:** Buy when close > highest high of last 20 bars AND volume > 1.5×
average. Exit via trailing stop (2×ATR) or 24-bar timeout.

### In-Sample Results (Apr–Sep 2026, 180 days, 1h)

| Pair | Trades | Win Rate | Return | Max DD | R:R |
|------|--------|----------|--------|--------|-----|
| XRP  | 56     | 39.3%    | +17.84% | -24.3% | 2.67 |
| SOL  | 61     | 41.0%    | +14.24% | -22.8% | 2.23 |
| ETH  | 62     | 40.3%    | +3.03%  | -28.0% | 1.65 |
| BNB  | 60     | 33.3%    | +2.37%  | -17.3% | 2.26 |
| BTC  | 65     | 40.0%    | +2.21%  | -22.6% | 1.68 |

**5/5 pairs positive. Median +3.03%. Average R:R > 2.0.**

This looked like a genuine edge. Time to validate out-of-sample.

### Out-of-Sample Results (Oct 2025–Mar 2026, 180 days, 1h)

| Pair | Trades | Win Rate | Return | Max DD |
|------|--------|----------|--------|--------|
| BNB  | 56     | 33.9%    | -5.74% | -43.5% |
| ETH  | 56     | 28.6%    | -7.28% | -45.1% |
| XRP  | 58     | 34.5%    | -8.10% | -41.3% |
| BTC  | 57     | 29.8%    | -8.95% | -37.6% |
| SOL  | 51     | 37.3%    | -11.93% | -49.2% |

**0/5 pairs positive. Median -8.10%.**

### Interpretation

**The strategy flipped from 5/5 positive to 0/5 positive** with identical
parameters on the same pairs. Only the market period changed.

The in-sample period (Apr–Sep 2026) was a crypto bull market. The OOS period
(Oct 2025–Mar 2026) was bearish/choppy. Breakout long-only works in trending
up markets — but that's not edge, that's beta to the underlying asset.

Critically:

- In bull markets, breakout **underperformed** buy-and-hold
- In bear markets, breakout **lost more** than buy-and-hold
- Max drawdowns in OOS were 2× the in-sample drawdowns

**The strategy is strictly worse than just holding the asset.**

---

## What We Learned

### 1. Fees Kill High-Frequency Strategies

At 5m, typical moves are 0.05–0.15%. Round-trip fees are 0.52%. You need
a move **3–10× larger than the average move** just to break even. This is
mathematically unwinnable with public signals.

### 2. In-Sample Results Are Usually Regime-Driven

Breakout's in-sample success was entirely explained by the bull market
period. This is the classic trap that retail traders fall into:

- Tune on a bull market
- Get lucky returns in backtest
- Deploy live
- Watch it lose when the regime changes

### 3. Sample Size Matters

The mean reversion "best combo" produced +8.01% from 7 trades. That's noise.
A strategy needs 30+ trades minimum for statistical significance, ideally
100+.

### 4. Out-of-Sample Validation Is Non-Negotiable

Without OOS testing, breakout would have been deployed live and lost money.
The OOS step is what separates serious research from curve-fitting.

### 5. Public Technical Indicators Are Arbitraged Away

This is the theoretical reason all three strategies failed. Millions of
traders use RSI, MACD, Bollinger, EMA crossovers. Any edge these tools
once had has been captured by faster/more sophisticated players.

**Real edges in crypto come from:**

- Non-public data (on-chain metrics, order flow, funding rates)
- Execution advantages (latency, co-location)
- Risk management (position sizing, correlation)
- Different asset classes (smaller caps, less liquid pairs)

Not from moving averages.

---

## What Works (Or Might)

**Breakout on 1h in trending markets** produced positive returns in the
in-sample period. With a **regime filter** (only trade when BTC is above
its daily EMA200), it might be tradeable as a bull-market strategy.

But it wouldn't beat buy-and-hold, and it wouldn't work in bear markets.
So it's not really a strategy — it's a slightly worse way to hold crypto.

**The next research direction** (out of scope for this project) is
**funding rate carry** on perpetual futures — a market-neutral strategy
that collects funding payments from leveraged traders. Documented
annualized returns: 5–15% with much lower volatility.

---

## Final Verdict

**Simple technical signals do not have edge on liquid crypto after fees.**

This project produced a rigorous negative result. That's valuable:

1. It prevents wasting capital on strategies that would fail live
2. It demonstrates correct research methodology (in-sample + OOS + fees)
3. It establishes a reusable framework for testing future ideas
4. It identifies the actual problem (fees, arbitrage) rather than blaming
   bugs or bad luck

If you're reading this as a portfolio piece: the point is the *methodology*,
not the *strategy*. The framework correctly separates real edge from noise
— which is the single most important skill in quantitative trading research.

---

## Appendix: Commands Used

All commands are available via the interactive menu (`python app.py`)
or directly:

**Single backtest:**

```powershell
python cli.py run --pair SOL/USDT --strategy breakout --timeframe 1h --days 180
```

**Batch across pairs/timeframes:**

```powershell
python batch.py --strategy breakout --pairs SOL/USDT,BTC/USDT,ETH/USDT,BNB/USDT,XRP/USDT --timeframes 5m,1h,4h
```

**Out-of-sample validation:**

```powershell
python oos_test.py --strategy breakout --end-date 2026-03-31
```

**Grid search (in research/):**

```powershell
python research/grid_search_v2.py meanrev
```

**Split-sample test (in research/):**

```powershell
python research/split_test.py
```