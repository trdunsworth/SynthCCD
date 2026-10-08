# Queueing & Game Theory Guide for PSAP Staffing Models

A checklist and primer for evaluating queueing models against the realities
of a 9-1-1 PSAP, including game-theoretic effects and the critiques of
Erlang-based staffing in the Tom Robbins literature.

## 1. Game-theoretic elements the model should account for

Queue-centric game theory treats callers and the centre as players with
strategies:

- **Balking** — callers who observe (or anticipate) a long queue choose not
  to enter (hang up at welcome message, use a different channel). Each
  join/balk decision is a player action; a Nash equilibrium joining
  probability exists for threshold strategies.
- **Reneging / patience** — time-in-queue triggers abandonment; equivalent
  to a time-dependent reneging strategy. Erlang A assumes exponential
  patience; real patience curves are closer to Weibull (Gans et al. 2003).
- **Redial / retry** — blocked or abandoned callers strategically redial,
  amplifying offered load (our Erlang-R fixed point). In game terms, redial
  is a repeated-game strategy with diminishing cost.
- **Jockeying / channel switching** — a caller bounced from the 911 trunk
  group may switch to a non-emergency line, SMS/RTT, or app; mode shifting
  equalizes perceived wait (Wardrop-style equilibrium across channels).
- **Priority manipulation** — callers asserting higher acuity than real to
  jump the queue; pushes toward non-preemptive priority models and the
  fairness metric in the evaluator.
- **Centre-side strategies** — the PSAP chooses staffing, routing, and
  announced expected waits. Announced ETAs are part of the game: honest
  estimates reduce redials and abandonment (a cooperation signal).

Model consequence: single-server FIFO with exogenous Poisson arrivals is a
s *degenerate* game with one passive player. Where redials, channel
switching, or announced ETAs are significant, the equilibrium offered load
is endogenous — matching why Erlang-R / fixed-point and PSA-style
evaluation matter.

## 2. Checklist: examining a queueing model for PSAP fit

For each candidate model, record:

1. **Arrival process** — Poisson? stationary? bursty/nonstationary?
   Does it survive a burst scenario (multi-casualty incident)?
2. **Service process** — exponential AHT? SCV of talk time? warm/cold
   transfer handling?
3. **Abandonment / patience** — none (C), exponential (A), none but balking,
   Weibull (better fit)?
4. **Capacity / loss** — infinite queue (C/A), bounded (K), loss (B)?
5. **Source model** — infinite population or finite units (Engset for
   radio/channels)?
6. **Routing / skills** — single pool, overlapping pools with priorities,
   discrete pools, hybrid (EFPA)?
7. **Stability conditions** — ρ < 1 required? overloaded regime handled?
8. **Behaviour under uncertainty** — how do errors scale with forecast error
   in arrival rate (Robbins: dominant driver)?
9. **Small-system accuracy** — error grows for small pools and high
   utilization (Robbins); QED-regime models (square-root) are built for this.
10. **Nonstationarity** — SIPP/PSA assumption that steady state holds per
    interval; validate against transient ramp-up.
11. **Output metrics** — SL threshold definition (answered within X s), ASA,
    abandonment rate, occupancy, pool blocking, per-route fairness.

## 3. Tom Robbins critiques — what our evaluation must capture

From Robbins' papers (ECU) evaluating Erlang C/A against simulation:

- **Erlang C assumptions are questionable** for real call centres: no
  abandonment, known stationary arrival rate, exponential talk time,
  infinite patience.
- **Erlang C is pessimistically biased on average** (real system performs
  better than predicted → overstaffing), but becomes optimistically biased
  when utilization is high and arrival rates are uncertain.
- **Erlang A is usually more accurate** (lower average error) but tends to
  be *optimistically biased* (→ understaffing risk), driven largely by
  arrival-rate uncertainty; high balking makes A preferable over C.
- **Erlang A in high-traffic (ρ > 1) regions flips to pessimistically
  biased** with moderate-to-high error, again dominated by arrival-rate
  uncertainty and balking.
- **Error drivers ranked:** offered utilization, agent pool size, arrival
  rate uncertainty/variability, probability of balking; patience shape and
  talk-time variability matter less.
- **SIPP/PSA-style pointwise stationary staffing ignores uncertainty and
  abandonment.** Robbins' SCCS (stochastic call centre scheduling) argues
  for scenario-based optimization over arrival patterns, joining server
  sizing and scheduling into one SLA objective; using abandonment without
  uncertainty may not improve results (two biases can cancel).
- **Practical implication:** never staff from a single model's point
  recommendation. Present the C/A spread, flag when utilization is high or
  the arrival forecast is uncertain, and prefer the conservative bound for
  strict SLAs.

## 4. Consequences for our evaluator

- Always compute Erlang C *and* Erlang A side by side and report the spread.
- Run with perturbed arrival rates (± forecast error scenarios) and record
  SL sensitivity — this is the single largest error driver.
- Include a balking probability parameter in PSA staffing comparisons.
- For ρ ≥ 1 scenarios, require Erlang A (C is undefined); report A's
  optimistic/pessimistic shift across load regimes.
- Treat Engset/Erlang-R as the "game-aware" corrections for radio and
  redial-heavy conditions, and compare their recommendations to Erlang C/A.
- Report metrics per pool and per route (EFPA), including priority fairness
  for common pools, rather than a single centre-wide SL.
