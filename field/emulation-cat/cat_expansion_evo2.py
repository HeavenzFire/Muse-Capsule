#!/usr/bin/env python3
"""Supplementary evolution: start OUTSIDE the cat manifold.
Initial states: vacuum |0> (even) and Fock |1> (odd), alpha=2.0,
k1=0.01, N=30, same engineered L as cat_expansion.py.
Question: how fast does the state confine to the manifold, and
does it then stay there (metastable) rather than mixing?
Method: exact propagation via eigendecomposition of L, same as
cat_expansion.py. Trace reported BEFORE renormalisation.
"""
import json
import time

import numpy as np
from scipy import linalg

import sys
sys.path.insert(0, "/home/hatch/workspace/field/scratch-cat-gkp")
from cat_expansion import liouvillian, spectrum, cat_states


def evolve(N, alpha, k1, psi0, times):
    L, _ = liouvillian(N, alpha, k1)
    vals, vecs = spectrum(L, N)
    rho0 = np.outer(psi0, psi0.conj())
    coeffs = linalg.solve(vecs, rho0.reshape(-1, order="F"))
    cplus, cminus = cat_states(N, alpha)
    P = np.outer(cplus, cplus.conj()) + np.outer(cminus, cminus.conj())
    rows = []
    for t in times:
        rho_vec = vecs @ (coeffs * np.exp(vals * t))
        rho = rho_vec.reshape((N, N), order="F")
        rho = 0.5 * (rho + rho.conj().T)
        tr = float(np.trace(rho).real)
        rho = rho / max(tr, 1e-300)
        manifold = float(np.trace((P @ rho @ P)).real)
        rows.append({
            "t_device": t, "trace_before_renorm": tr,
            "leakage": 1.0 - manifold, "manifold_pop": manifold,
            "pop_even_cat": float(np.real(cplus.conj() @ rho @ cplus)),
            "pop_odd_cat": float(np.real(cminus.conj() @ rho @ cminus)),
            "purity": float(np.real(np.trace(rho @ rho))),
        })
    return rows


def main():
    times = [0.0, 0.1, 0.5, 1.0, 5.0, 20.0, 100.0, 1000.0]
    out = {}
    for name, n in [("vacuum_0", 0), ("fock_1", 1)]:
        t0 = time.time()
        psi0 = np.zeros(30, dtype=complex)
        psi0[n] = 1.0
        rows = evolve(30, 2.0, 0.01, psi0, times)
        out[name] = rows
        print(name, "wall_s", round(time.time() - t0, 2), flush=True)
        for r in rows:
            print(json.dumps({"init": name, **r}), flush=True)
    with open("cat_expansion_evo2.json", "w") as f:
        json.dump(out, f, indent=1)
    print("WROTE cat_expansion_evo2.json", flush=True)


if __name__ == "__main__":
    main()
