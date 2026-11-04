#!/usr/bin/env python3
"""Cat expansion beyond run 4 — NOT a replication.

Starts from cat_layer1.py's engineered dissipator
  L_cat = sqrt(k2) (a^2 - alpha^2),  k2 = 1.0
  H = -Delta a^dagger a + (K/2) a^dagger^2 a^2 + eps2 (a^dagger^2 + a^2)
  L(rho) = -i[H, rho] + k1 D[a] rho + D[L_cat] rho
with the run-4 operating point Delta=0, K=0.2, eps2 = -alpha^2 K/2
(real-alpha cats, eps2 < 0, as corrected in run 4).

What run 4 did NOT settle, and this file does:
  (a) The degenerate parity-sector manifold for alpha=2.0/2.5.
      Run 4's gap metric was misleading for degenerate cases: it
      excluded eigenvalues with |lambda| < 1e-7 and then reported the
      NEXT mode as "the gap". Here the full sorted spectrum is
      reported: lam0, lam1, lam2 magnitudes, so a second near-zero
      mode is visible, not hidden. A manifold is called degenerate
      at threshold T if lam1 < T. Two thresholds are reported:
      T=1e-6 (run-4 threshold) and T=1e-4 (a practical uniqueness
      threshold: a mode slower than 1e-4 takes >1e4 time units
      to decay, i.e. it is a second steady state for every
      practical evolution time).
  (b) Time-dilated evolution of the cat manifold: exact propagation
      via the eigendecomposition of L (same L, no new physics),
      from a coherent initial state, showing fast confinement
      (kappa2 timescale) followed by the extremely slow parity
      equilibration (1/gap timescale). Device time t is in units
      of 1/kappa2 (kappa2 = 1.0); wall time is measured and the
      device/wall ratio is reported as the dilation achieved
      in this numerical run — not a hardware claim.
  (c) Degeneracy breaking: (i) k1 alone, swept; (ii) a parity-
      breaking single-photon drive eps1 (a + a^dagger) added to H.
      Does the steady state select one cat (purity -> 1) or stay
      a mixture (purity ~ 0.5)? What gap, leakage, fidelity?
  (d) F1 vs cutoff: r_dark for alpha=2.5 at N > 30, which run 4
      never ran. (Spoiler, verified before this file was written:
      r_dark+ = 7.66e-07 at N=36, 2.25e-08 at N=40 — F1 PASSES
      at N >= 36. The run-4 F1 FAIL at N=30 was a truncation
      artifact, not a physics failure. That claim is re-verified
      inside this script, not taken on trust.)

Thresholds (same as run 4, plus the honest additions above):
  F1 r_dark+ < 1e-6 ; F2 r_steady < 1e-8 ; F5 gap > 0, where
  gap here means lam1 (the slow mode), reported exactly, not
  through the run-4 exclusion filter.

Usage: python3 cat_expansion.py
Output: JSON to stdout + cat_expansion_results.json alongside.
Requires: numpy, scipy (system python3).
"""
import json
import sys
import time

import numpy as np
from scipy import linalg


def annihilation(N):
    a = np.zeros((N, N), dtype=complex)
    for n in range(1, N):
        a[n - 1, n] = np.sqrt(n)
    return a


def coherent(N, alpha):
    v = np.zeros(N, dtype=complex)
    v[0] = np.exp(-0.5 * abs(alpha) ** 2)
    for k in range(1, N):
        v[k] = v[k - 1] * alpha / np.sqrt(k)
    return v / np.linalg.norm(v)


def cat_states(N, alpha):
    cp = coherent(N, alpha)
    cm = coherent(N, -alpha)
    plus = cp + cm
    minus = cp - cm
    return plus / np.linalg.norm(plus), minus / np.linalg.norm(minus)


def dissipator(L):
    Lc = L.conj()
    return (np.kron(Lc, L)
            - 0.5 * np.kron(np.eye(L.shape[0]), L.conj().T @ L)
            - 0.5 * np.kron((L.conj().T @ L).T, np.eye(L.shape[0])))


def liouvillian(N, alpha, k1, k2=1.0, K=0.2, eps1=0.0, Delta=0.0):
    """Engineered L_cat only. eps1 is the parity-breaking drive,
    zero unless a degeneracy-breaking experiment asks for it."""
    a = annihilation(N)
    ad = a.conj().T
    eps2 = -alpha ** 2 * K / 2.0
    H = (-Delta * (ad @ a) + 0.5 * K * (ad @ ad @ a @ a)
         + eps2 * (ad @ ad + a @ a) + eps1 * (a + ad))
    I = np.eye(N)
    jump = np.sqrt(k2) * (a @ a - alpha ** 2 * I)
    L = (-1j * (np.kron(I, H) - np.kron(H.T, I))
         + k1 * dissipator(a) + dissipator(jump))
    return L, a


def spectrum(L, N):
    vals, vecs = linalg.eig(L)
    order = np.argsort(np.abs(vals))
    vals = vals[order]
    vecs = vecs[:, order]
    return vals, vecs


def vec_to_rho(vec, N):
    rho = vec.reshape((N, N), order="F")
    rho = 0.5 * (rho + rho.conj().T)
    tr = np.trace(rho).real
    if abs(tr) < 1e-300:
        return rho
    return rho / tr


def steady_metrics(L, rho, N, alpha):
    Lrho = (L @ rho.reshape(-1, order="F")).reshape((N, N), order="F")
    r_steady = float(np.sum(np.linalg.svd(Lrho, compute_uv=False)))
    cplus, cminus = cat_states(N, alpha)
    P = np.outer(cplus, cplus.conj()) + np.outer(cminus, cminus.conj())
    PrhoP = P @ rho @ P
    leak = 1.0 - float(np.trace(PrhoP).real)
    rho_L = PrhoP / max(np.trace(PrhoP).real, 1e-300)
    fid_plus = float(np.real(cplus.conj() @ rho_L @ cplus))
    fid_minus = float(np.real(cminus.conj() @ rho_L @ cminus))
    return {
        "r_steady": r_steady,
        "trace": float(np.trace(rho).real),
        "min_eig": float(np.min(np.linalg.eigvalsh(rho))),
        "leakage": leak,
        "fid_plus_in_manifold": fid_plus,
        "fid_minus_in_manifold": fid_minus,
        "purity": float(np.real(np.trace(rho @ rho))),
    }


def analyse_case(N, alpha, k1, eps1=0.0, label=""):
    t0 = time.time()
    L, a = liouvillian(N, alpha, k1, eps1=eps1)
    vals, vecs = spectrum(L, N)
    mags = [float(np.abs(v)) for v in vals[:6]]
    lam1 = mags[1] if len(mags) > 1 else None
    out = {
        "label": label, "N": N, "alpha": alpha, "k1": k1, "eps1": eps1,
        "lam_mags_first6": mags,
        "lam1": lam1,
        "degenerate_1e-6": bool(lam1 is not None and lam1 < 1e-6),
        "degenerate_1e-4": bool(lam1 is not None and lam1 < 1e-4),
        "wall_s": round(time.time() - t0, 2),
    }
    # Unique steady state only if lam1 is above the run-4 threshold.
    if lam1 is not None and lam1 >= 1e-6:
        rho = vec_to_rho(vecs[:, 0], N)
        out.update(steady_metrics(L, rho, N, alpha))
        out["steady_unique"] = True
    else:
        out["steady_unique"] = False
        out["note"] = ("lam1 below 1e-6: no unique steady state at "
                       "run-4 threshold; slow parity mode persists")
    print(json.dumps(out), flush=True)
    return out, L, vals, vecs


def sector_steady(N, alpha, k1, parity):
    """Steady state restricted to one parity sector, k1=0 only
    (k1 mixes sectors, so restriction is only meaningful at k1=0).
    Returns leakage/fidelity of that sector's steady state."""
    L, a = liouvillian(N, alpha, k1)
    idx = [n for n in range(N) if (n % 2 == 0) == (parity == "even")]
    # Build restricted Liouvillian by projecting the full L onto the
    # sector's vectorised basis: basis e_{i,j} with i,j in idx.
    # Simpler and exact at k1=0: diagonalise the restricted H+dissipator
    # by using the full L but zeroing cross-sector couplings is not
    # trivial; instead use the cat state itself: at k1=0 the sector
    # steady state is the cat of that parity (dark state), and we
    # verify it directly: ||L rho_cat|| and leakage.
    cplus, cminus = cat_states(N, alpha)
    cat = cplus if parity == "even" else cminus
    rho = np.outer(cat, cat.conj())
    m = steady_metrics(L, rho, N, alpha)
    m["parity"] = parity
    m["N"] = N
    m["alpha"] = alpha
    m["k1"] = k1
    return m


def time_evolution(N, alpha, k1, times):
    """Exact propagation via eigendecomposition of L.
    Initial state: coherent |alpha> (a superposition of both cats).
    Returns leakage, manifold population, even/odd cat populations,
    purity at each device time. Wall time measured."""
    t_wall0 = time.time()
    L, a = liouvillian(N, alpha, k1)
    vals, vecs = spectrum(L, N)
    # Solve vecs @ c = rho0_vec
    psi0 = coherent(N, alpha)
    rho0 = np.outer(psi0, psi0.conj())
    rho0_vec = rho0.reshape(-1, order="F")
    coeffs = linalg.solve(vecs, rho0_vec)
    cplus, cminus = cat_states(N, alpha)
    P = np.outer(cplus, cplus.conj()) + np.outer(cminus, cminus.conj())
    rows = []
    for t in times:
        factors = np.exp(vals * t)
        rho_vec = vecs @ (coeffs * factors)
        rho = rho_vec.reshape((N, N), order="F")
        rho = 0.5 * (rho + rho.conj().T)
        # Trace before renormalisation = conservation check
        tr_before = float(np.trace(rho).real)
        rho = rho / max(tr_before, 1e-300)
        PrhoP = P @ rho @ P
        manifold = float(np.trace(PrhoP).real)
        rows.append({
            "t_device": t,
            "trace_before_renorm": tr_before,
            "leakage": 1.0 - manifold,
            "manifold_pop": manifold,
            "pop_even_cat": float(np.real(cplus.conj() @ rho @ cplus)),
            "pop_odd_cat": float(np.real(cminus.conj() @ rho @ cminus)),
            "purity": float(np.real(np.trace(rho @ rho))),
        })
    wall = time.time() - t_wall0
    return rows, wall


def main():
    results = {"cases": [], "sector": [], "evolution": [], "f1_vs_N": []}

    # --- (d) F1 vs N, re-verified inside this script ---
    print("=== F1 vs N ===", flush=True)
    for alpha in (1.5, 2.0, 2.5):
        for N in (24, 30, 36, 40, 48):
            a = annihilation(N)
            cp, cm = cat_states(N, alpha)
            I = np.eye(N)
            row = {"alpha": alpha, "N": N,
                   "r_dark_plus": float(np.linalg.norm((a @ a - alpha ** 2 * I) @ cp)),
                   "r_dark_minus": float(np.linalg.norm((a @ a - alpha ** 2 * I) @ cm)),
                   "F1_pass": bool(np.linalg.norm((a @ a - alpha ** 2 * I) @ cp) < 1e-6)}
            results["f1_vs_N"].append(row)
            print(json.dumps(row), flush=True)

    # --- (a) spectrum vs k1, N=30 ---
    print("=== Spectrum vs k1, N=30 ===", flush=True)
    for alpha in (1.5, 2.0, 2.5):
        for k1 in (0.0, 0.001, 0.003, 0.01, 0.03, 0.1, 0.3):
            out, _, _, _ = analyse_case(30, alpha, k1, label="spectrum_vs_k1")
            results["cases"].append(out)

    # --- (a) spectrum vs N for alpha=2.5, k1=0.01 (and 2.0) ---
    print("=== Spectrum vs N, k1=0.01 ===", flush=True)
    for alpha in (2.0, 2.5):
        for N in (36,):
            out, _, _, _ = analyse_case(N, alpha, 0.01, label="spectrum_vs_N")
            results["cases"].append(out)

    # --- sector steady states at k1=0 ---
    print("=== Parity-sector steady states, k1=0, N=30 ===", flush=True)
    for alpha in (2.0, 2.5):
        for parity in ("even", "odd"):
            row = sector_steady(30, alpha, 0.0, parity)
            results["sector"].append(row)
            print(json.dumps(row), flush=True)

    # --- (c) degeneracy breaking by eps1 drive ---
    print("=== eps1 parity-breaking drive, N=30, k1=0.01 ===", flush=True)
    for alpha in (2.0, 2.5):
        for eps1 in (0.0, 0.01, 0.05, 0.1, 0.2):
            out, _, _, _ = analyse_case(30, alpha, 0.01, eps1=eps1,
                                         label="eps1_breaking")
            results["cases"].append(out)

    # --- (b) time-dilated evolution, alpha=2.0, k1=0.01, N=30 ---
    print("=== Time evolution, alpha=2.0, k1=0.01, N=30, init |alpha> ===", flush=True)
    times = [0.0, 0.1, 0.5, 1.0, 5.0, 20.0, 100.0, 1000.0, 10000.0, 100000.0]
    rows, wall = time_evolution(30, 2.0, 0.01, times)
    for row in rows:
        print(json.dumps(row), flush=True)
    results["evolution"] = {"N": 30, "alpha": 2.0, "k1": 0.01,
                            "init": "coherent |alpha>", "wall_s": wall,
                            "device_times": rows,
                            "dilation_device_over_wall":
                                (max(times) / wall if wall > 0 else None)}
    print(json.dumps({"evolution_wall_s": wall,
                      "max_device_time": max(times)}), flush=True)

    with open("cat_expansion_results.json", "w") as f:
        json.dump(results, f, indent=1)
    print("WROTE cat_expansion_results.json", flush=True)


if __name__ == "__main__":
    main()
