# Cat qubit emulation — EXPANSION, not replication

**Status: EXPANSION beyond run 4. Layer 1 is still NOT formally passed
overall. No GKP claim follows from this run.**

This run starts from `cat_layer1.py`'s engineered dissipator, unchanged:
`L_cat = sqrt(kappa2) (a^2 - alpha^2)`, kappa2 = 1.0,
`H = -Delta a^dagger a + (K/2) a^dagger^2 a^2 + eps2 (a^dagger^2 + a^2)`,
`Delta = 0, K = 0.2, eps2 = -alpha^2 K / 2` (real-alpha cats),
plus `k1 D[a]`. No textbook re-derivation, no DRAG, no generic harness.

Files in this folder (GitHub: `field/emulation-cat/`):
- `cat_expansion.py` — spectrum, sector, eps1-breaking, and
  coherent-state evolution experiments.
- `cat_expansion_evo2.py` — evolution from OUTSIDE the manifold
  (vacuum |0>, Fock |1>).
- `cat_expansion_results.json` — all main-run numbers.
- `cat_expansion_evo2.json` — all outside-manifold evolution numbers.

## 1. What run 4 got wrong, and what this run corrects

Run 4's gap metric excluded eigenvalues with |lambda| < 1e-7 and then
reported the NEXT mode as "the gap". For alpha=2.0, k1=0.01, run 4
reported gap = 0.0799. That is lam2, not the slow mode. The true
slow mode is lam1 = 4.83e-08 — six orders of magnitude slower.
Every gap in this report is the full sorted spectrum: lam0, lam1,
lam2, ... reported exactly, so a second near-zero mode is visible,
not hidden.

At k1=0, the first FOUR eigenvalues are ~1e-13, not two. The
steady operator manifold is 4-dimensional: two cat populations
(even, odd) plus two cat coherences. Single-photon loss splits
that manifold into two very different timescales (see §3), and
run 4's "n_steady = 2" counted only the population part of it.

## 2. F1 vs cutoff — run 4's alpha=2.5 FAIL was truncation, not physics

r_dark+ = ||(a^2 - alpha^2)|C+>||, threshold < 1e-6:

| alpha | N=24 | N=30 | N=36 | N=40 | N=48 |
|---|---|---|---|---|---|
| 1.5 | 2.29e-07 PASS | 1.59e-10 PASS | 5.80e-14 | 3.19e-16 | 2.31e-16 |
| 2.0 | 9.58e-05 FAIL | 3.72e-07 PASS | 7.65e-10 | 9.20e-12 | 9.74e-16 |
| 2.5 | 6.58e-03 FAIL | 9.76e-05 FAIL | 7.66e-07 PASS | 2.25e-08 PASS | 1.06e-11 PASS |

**F1 for alpha=2.5 PASSES at N >= 36.** Run 4 stopped at N=30, so
its F1 FAIL for alpha=2.5 is superseded. This does not pass Layer 1
overall (see §6), because F1 is only one criterion.

## 3. The degenerate manifold, properly resolved: TWO timescales

lam1 = slow coherence mode. lam2 = parity-population mixing mode.
N=30, k1=0.01:

| alpha | lam1 (timescale 1/lam1) | lam2 (timescale 1/lam2) | ratio |
|---|---|---|---|
| 1.5 | 7.05e-06 (1.42e5) | 0.0449 (22.3) | 6,400x |
| 2.0 | 4.83e-08 (2.07e7) | 0.0799 (12.5) | 1,700,000x |
| 2.5 | 3.01e-09 (3.32e8) | 0.1249 (8.0) | 41,000,000x |

lam1 vs k1, N=30 (lam1 stays below 1e-4 for every alpha >= 2.0 case
tested, and below 1e-6 for alpha=2.5 even at k1=0.3):

| k1 | alpha=1.5 lam1 | alpha=2.0 lam1 | alpha=2.5 lam1 |
|---|---|---|---|
| 0.0 | ~1e-13 | ~1e-13 | ~1e-13 |
| 0.001 | 5.70e-07 | 1.29e-09 | 2.63e-09 |
| 0.003 | 1.80e-06 | 6.19e-09 | 2.66e-09 |
| 0.01 | 7.05e-06 | 4.83e-08 | 3.01e-09 |
| 0.03 | 3.04e-05 | 3.92e-07 | 6.40e-09 |
| 0.1 | 2.16e-04 | 4.63e-06 | 5.20e-08 |
| 0.3 | 1.84e-03 | 5.56e-05 | 6.74e-07 |

lam2 scales roughly as 8*k1 for alpha=2.0 (0.008, 0.024, 0.080,
0.239, 0.790, 2.301 across the same k1 sweep) — that is the
single-photon parity-flip rate, and it is NOT suppressed with alpha.

Spectrum vs cutoff: at N=36, k1=0.01, lam1 = 4.828e-08 for
alpha=2.0 (identical to N=30 to 5 significant figures — converged)
and 4.10e-10 for alpha=2.5 (vs 3.01e-09 at N=30 — same order,
far below threshold, but the exact alpha=2.5 lam1 value is NOT
yet converged; an N=40 spectrum was not run, and is not claimed).

**Reading:** k1 alone does NOT break the degeneracy in any
practical sense for alpha >= 2.0. A "unique steady state" by the
1e-6 threshold (alpha=2.0 at k1=0.1, lam1=4.63e-06) is a threshold
artifact: at any evolution time below ~1e5, the lam1 mode is
frozen, and the state behaves as if the manifold were degenerate.

## 4. Parity-sector steady states at k1=0

Even cat |C+> and odd cat |C->, each alone: purity = 1.0,
leakage ~0 (within 1e-15), fidelity 1.0 to its own sector, 0.0 to
the other. They are dark states of L_cat. But they are NOT exact
steady states of the FULL Liouvillian (H also acts), and the
residual r_steady = ||L rho||_1 is truncation-limited:

| alpha | N=30 even / odd | N=36 even / odd | N=40 even / odd |
|---|---|---|---|
| 2.0 | 1.52e-06 / 5.64e-07 | 3.12e-09 / 1.06e-09 | 3.75e-11 / 1.20e-11 |
| 2.5 | 6.22e-04 / 2.89e-04 | 4.88e-06 / 2.06e-06 | 1.43e-07 / 5.73e-08 |

F2 for sector cats (< 1e-8): alpha=2.0 passes at N >= 36;
alpha=2.5 does NOT pass even at N=40 (1.43e-07). It is falling
fast with N, but a pass at larger N is NOT claimed — it was not run.

## 5. Degeneracy breaking by a parity-breaking drive: NEGATIVE result

Adding eps1*(a + a^dagger) to H, N=30, k1=0.01. It lifts lam1,
but it does NOT select a single cat:

alpha=2.0: eps1 0 -> lam1 4.83e-08; 0.01 -> 8.73e-08;
0.05 -> 1.02e-06 (unique by 1e-6, still < 1e-4); 0.1 -> 3.96e-06;
0.2 -> 1.59e-05. At every eps1 where a unique steady state exists,
fid_plus ~ 0.500, fid_minus ~ 0.500, purity ~ 0.50-0.51 — the
equal mixture, not a single cat. Leakage GROWS with eps1:
5.18e-05 (0.05) -> 2.01e-04 (0.1) -> 7.98e-04 (0.2).

alpha=2.5: lam1 stays below 1e-6 even at eps1=0.2 (1.09e-07);
no unique steady state at the run-4 threshold at any eps1 tested.

**Conclusion: a single-photon drive is not a cat selector.** It
accelerates coherence decay without picking a parity sector.
A selector, if one exists, needs a different mechanism (e.g. a
parity-conditioned drive or measurement) — not proposed here,
because it was not tested.

## 6. Time-dilated evolution: confinement fast, coherence metastable

Method: exact propagation via eigendecomposition of L (same L,
no new physics). Device time t is in units of 1/kappa2 (kappa2 =
1.0). Wall time is measured; the dilation figure is the device
time span covered per wall second for this numerical method —
not a hardware speed claim.

(a) From INSIDE the manifold — coherent |alpha>, alpha=2.0,
k1=0.01, N=30: leakage stays ~2e-06, manifold population ~1.0,
at every time from 0 to 1e5. Purity falls only 1.000 -> 0.995 at
t=1e5, even/odd populations stay 0.5003 / 0.4997. That matches
exp(-lam1 * t) = exp(-0.0048) = 0.995 at t=1e5, with
1/lam1 = 2.07e7. The coherent cat state is metastable for
~1e7 device time units, not for ~12.

(b) From OUTSIDE the manifold — vacuum |0> and Fock |1>,
alpha=2.0, k1=0.01, N=30: leakage 0.963 / 0.853 at t=0, falling
to 0.031 / 0.00018 at t=1, and ~2e-06 by t=5. Manifold population
reaches ~1.0 by t=5 (confinement timescale ~ kappa2^-1, a few
units). Populations then mix to 0.500 / 0.500 by t=100, purity
to 0.500 by t=100 — the lam2 timescale (12.5), not lam1.

**Two timescales, one manifold:** confinement in ~5 units,
population mixing in ~12 units, coherence survival in ~2e7 units
at alpha=2.0. A steady-state snapshot (purity 0.5) hides all of
this: it describes t -> infinity, not any time a real device
would actually run.

## 7. Verification

- Steady metrics where a unique steady state exists (lam1 >= 1e-6):
  r_steady ~ 6e-12 (F2 PASS, < 1e-8), trace-1 ~ 1e-16, min
  eigenvalue ~ -1e-15 (numerical zero).
- Trace before renormalisation in evolution: within 5e-10 up to
  t=1000, 4.9e-08 at t=1e5 (eig-propagation numerical error at
  very large t, reported, not hidden).
- All numbers in the JSON files are output of running the code,
  not hand-written. Population/conservation checks were measured
  on raw propagated states before renormalisation.
- Wall times: ~14 s per N=30 dense eig, ~40 s per N=36 eig,
  14.9 s for the coherent evolution (10 time points to 1e5).

## 8. Layer 1 verdict after expansion — still NOT passed

- F1: alpha=2.5 now PASSES at N >= 36 (supersedes run 4's N=30 FAIL).
- Unique steady state at practical thresholds: FAILS for
  alpha >= 2.0 at k1 <= 0.1 (lam1 < 1e-4), and for alpha=2.5
  even at k1=0.3 and eps1=0.2 (lam1 < 1e-6).
- Sector F2: alpha=2.5 FAILS even at N=40.
- Therefore: **no Layer 1 pass claim, no GKP claim.** What this
  expansion changes is the INTERPRETATION, not the verdict: the
  manifold is not a failed unique steady state — it is a
  metastable qubit whose coherence timescale (lam1) is
  exponentially long in alpha, while its population mixing
  timescale (lam2) is fast. An encoding that uses cat coherence
  lives on the lam1 timescale; an encoding that uses cat
  populations lives on the lam2 timescale. Which encoding Layer 2
  (GKP) needs, and whether it can live on lam1, is the next
  question — it is NOT answered here.

## 9. What was NOT verified

- No real hardware was run. No specific device, chip, or lab
  result is claimed or reproduced.
- No N=40 spectrum (lam1 convergence for alpha=2.5 is open).
- No parity-conditioned selector was tested.
- No GKP encoding was added, and no GKP threshold was evaluated.
- T1/T2 decoherence was not included in this run (unitary +
  engineered dissipator + k1 only, as in run 4).
- The dilation figure is a numerical-method figure, not a
  hardware rate.

## Parameters (complete, for reproduction)

alpha in {1.5, 2.0, 2.5}; N in {24, 30, 36, 40, 48} for F1,
{30, 36} for spectra, {30, 36, 40} for sector residuals;
Delta = 0; K = 0.2; eps2 = -alpha^2 K/2; kappa2 = 1.0;
k1 in {0, 0.001, 0.003, 0.01, 0.03, 0.1, 0.3};
eps1 in {0, 0.01, 0.05, 0.1, 0.2} for breaking experiments.
Engineered dissipator only (CAT_ENGINEERED logic inlined from
cat_layer1.py, no environment dependency).
