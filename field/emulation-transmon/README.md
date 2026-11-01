# Transmon emulation — FIRST (emulated, not simulated)

Zachary's named first emulation target, tapped 2026-11-01. Cat qubit is
second and is NOT built here.

## What this is

Real Hamiltonian behaviour of a 3-level transmon (|0>, |1>, |2>), driven
by a shaped microwave pulse, evolved in nanoseconds of device time and
executed on a computer over seconds of wall time (time dilation — see
results.json). It is NOT a run on real hardware, NOT a hardware
measurement, and NOT a claim to equal any specific device.

## Parameters (stated, not fitted)

- alpha / 2pi = -250 MHz — midpoint of the typical -200 to -300 MHz
  transmon anharmonicity range.
- Gaussian in-phase pulse, sigma = 2.0 ns, window -10 to +10 ns
  (20 ns total device time), centre 0.
- Omega0 = pi / (sigma * sqrt(2pi)) = 0.627 rad/ns = 99.8 MHz cyclic,
  the pi-pulse area condition for the two-level part.
- Coupling: <0|a|1> = 1, <1|a|2> = sqrt(2).
- DRAG: Q(t) = -dI/dt / alpha, same pulse, same parameters, both legs.
- Decoherence leg (labelled, separate): T1 = 50 us, T2 = 30 us,
  Tphi = 42.9 us. Typical-order values, stated, not measured.

## Results — central parameters, unitary leg

| leg | final P1 (fidelity to |1>) | final P2 (leakage) | max P2 during drive |
| --- | --- | --- | --- |
| without DRAG | 0.9718 | 0.000717 | 0.0646 |
| with DRAG | 0.9694 | 0.0000018 | 0.0443 |

Read this carefully, because it is not a simple "DRAG wins everywhere"
story:

- DRAG suppresses *final* leakage by about 350x (0.072% -> 0.00018%).
- DRAG does NOT remove transient leakage: max P2 during the drive is
  still 4.4% with DRAG, vs 6.5% without. It returns the population at
  the end; it does not keep |2> empty throughout.
- DRAG does NOT improve final fidelity to |1> here (0.9718 -> 0.9694).
  The remaining error moves into residual P0 (2.7% -> 3.1%), because
  first-order DRAG without a detuning/area correction changes the
  effective pulse area. A fuller DRAG (with detuning correction) is a
  follow-up leg, not claimed here.

Decoherence leg: essentially identical (final P2 0.000721 without DRAG,
0.0000047 with DRAG; fidelity 0.9716 / 0.9692). Over 20 ns, 30–50 us
rates change populations by < 0.1%. That smallness is a result.

## Sensitivity (unitary, final P2)

Faster pulses and smaller |alpha| leak more, and DRAG helps most there:

- alpha -200 MHz, sigma 1.5 ns: 0.0633 -> 0.00139
- alpha -250 MHz, sigma 1.5 ns: 0.0152 -> 0.000161
- alpha -250 MHz, sigma 2.0 ns: 0.000717 -> 0.0000018
- alpha -300 MHz, sigma 2.0 ns: 0.000032 -> ~0
- alpha -250 MHz, sigma 3.0 ns: 0.000001 -> ~0

Full table in results.json; populations every 0.2 ns in populations.csv.

## Comparison to the screenshot (not a target)

The screenshot Zachary sent showed ~24.1% leakage over a 10 ns drive.
That is a comparison point only. This run uses a 20 ns window and
sigma = 2 ns, and its max transient leakage is 6.5% without DRAG —
same order of magnitude as a fast-pulse leak, not a reproduction.
A sigma = 1 ns leg in exploration gave max P2 ~27% and final P2
~14% without DRAG, which shows how strongly the number depends on
pulse speed; no parameter was tuned to land on 24.1%.

## Verification

- Unitary population conservation (raw RK4 step, before any
  renormalisation): max error ~1e-15.
- Lindblad trace conservation: max error ~1e-15.
- Pulse shape, populations, and sensitivity are all recomputed by
  running transmon.py; results.json and populations.csv are its output,
  not hand-written numbers.

## NOT verified

- No real hardware was run. No hardware measurement was reproduced.
- No claim this model equals any specific device, chip, or lab result.
- T1/T2 are assumptions, not measurements.
- DRAG here is first-order quadrature correction only; no detuning
  correction, no pulse distortion, no readout model.
- Time dilation: 20 ns of device time executed in ~3.4 s of wall time
  for all legs plus sensitivity in this run. That is magnification to
  computer timescale, not real-time execution and not a hardware
  speed claim.

## Files

- transmon.py — the emulation (unitary + Lindblad + sensitivity)
- results.json — data and numbers
- populations.csv — P0/P1/P2 every 0.2 ns, both unitary legs
