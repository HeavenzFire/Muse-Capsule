"""
Transmon emulation, FIRST — emulated, not simulated in Zachary's sense:
real Hamiltonian behaviour of a 3-level device, run at dilated time.

What this is:
  A 3-level transmon (|0>, |1>, |2>) driven by a shaped microwave pulse.
  The model evolves the actual state under the device Hamiltonian, in
  nanoseconds of device time, executed on a computer over a much longer
  wall-clock time (time dilation, see results.json). It is NOT a run on
  real hardware, NOT a hardware measurement, and NOT a claim to equal
  any specific device.

What this is not:
  - Not a cat qubit (cat is second, not first; not built here).
  - Not a generic harness. This file is this device only.
  - Not fitted to any screenshot. The ~24.1% leakage in the screenshot
    Zachary sent (10 ns drive, |1> -> |2> spillover) is a comparison
    point only. Parameters below were chosen before seeing the final
    numbers, from typical transmon values, and are stated in full.

Physics (rotating frame at the drive frequency, resonant with |0> <-> |1>):
  Levels: E0 = 0, E1 = 0 (rotating frame), E2 = alpha.
  alpha / 2pi = -250 MHz — the midpoint of the typical -200 to -300 MHz
  transmon anharmonicity range. Chosen because it is central, not
  because it matches any one device.
  Drive: Gaussian in-phase component
      I(t) = Omega0 * exp(-(t-tc)^2 / (2 sigma^2)),  sigma = 2.0 ns,
      tc = 0 (window -10 to +10 ns, 20 ns total device time).
      Omega0 is set so the pulse area is pi: Omega0 = pi / (sigma*sqrt(2pi))
      = 0.627 rad/ns = 99.8 MHz (cyclic). That is the |0> -> |1> pi-pulse
      condition for the two-level part; leakage to |2> is what is measured.
  Coupling: annihilation operator a has matrix elements <0|a|1> = 1,
      <1|a|2> = sqrt(2). The drive term is
      H_drive = (I/2)(a + a^dagger) + (iQ/2)(a^dagger - a),
      i.e. the complex envelope I + iQ.
  DRAG (derivative removal by adiabatic gate):
      Q(t) = - dI/dt / alpha,  alpha in rad/ns.
      Without DRAG, Q = 0. Same pulse, same parameters, both legs.
  Why DRAG helps here: the quadrature component cancels, to first
  order, the spectral weight of the drive at the |1> <-> |2> frequency
  (detuned by alpha), which is what populates |2>.

Evolution:
  Leg A (main): unitary Schrodinger evolution, RK4, dt = 0.01 ns.
  Leg B (labelled decoherence leg, same pulse, same DRAG on/off):
      Lindblad master equation for the density matrix, RK4, dt = 0.01 ns,
      T1 = 50 us, T2 = 30 us (typical-order transmon values, stated, not
      measured here). Collapse operators: relaxation sqrt(1/T1) * a, and
      pure dephasing with Tphi from 1/T2 = 1/(2*T1) + 1/Tphi
      (Tphi = 42.9 us), operator sqrt(1/Tphi) * diag(0, 1, 2).
      Over a 20 ns pulse these rates change populations by < 0.1% —
      that smallness is a result, not an assumption hidden in the code.

Verification (computed in this script, reported in results.json):
  - Unitary population conservation: |P0+P1+P2 - 1| at every step.
  - Lindblad trace conservation: |Tr(rho) - 1|.
  - Final fidelity to the intended |1> state: unitary |<1|psi>|^2,
    Lindblad rho[1,1].
  - Sensitivity: final P2 with/without DRAG for alpha/2pi in
    {-200, -250, -300} MHz and sigma in {1.5, 2.0, 3.0} ns.

Time dilation (Zachary's terms):
  Device time is nanoseconds. Wall-clock time is measured and reported.
  The ratio wall_time / device_time is the dilation: ns device dynamics
  magnified to computer/human timescale. No claim of real-time execution
  and no claim of hardware speed is made.
"""

import json
import time

import numpy as np

SQRT2 = np.sqrt(2.0)
A = np.array([[0, 1, 0], [0, 0, SQRT2], [0, 0, 0]], dtype=complex)
AD = A.T.conj()
N_OP = np.diag([0.0, 1.0, 2.0]).astype(complex)

# --- central parameters (stated, not fitted) ---
ALPHA_MHZ = -250.0          # alpha / 2pi, MHz; midpoint of -200..-300
SIGMA_NS = 2.0              # Gaussian width, ns
T_MIN, T_MAX, DT = -10.0, 10.0, 0.01   # device-time window, ns
T1_US, T2_US = 50.0, 30.0   # decoherence leg only, us


def alpha_rad_per_ns(alpha_mhz):
    # MHz = 1/us; convert to rad/ns: MHz * 2pi / 1000
    return 2.0 * np.pi * alpha_mhz / 1000.0


def pulse(t, sigma, alpha):
    """Return (I, Q) in rad/ns at device time t (ns, centre 0)."""
    omega0 = np.pi / (sigma * np.sqrt(2.0 * np.pi))
    i_comp = omega0 * np.exp(-(t ** 2) / (2.0 * sigma ** 2))
    i_dot = -(t / sigma ** 2) * i_comp
    q_comp = -i_dot / alpha
    return i_comp, q_comp


def hamiltonian(t, sigma, alpha, drag):
    i_comp, q_comp = pulse(t, sigma, alpha)
    if not drag:
        q_comp = 0.0
    h = np.diag([0.0, 0.0, alpha]).astype(complex)
    h = h + (i_comp / 2.0) * (A + AD) + (1j * q_comp / 2.0) * (AD - A)
    return h


def run_unitary(sigma=SIGMA_NS, alpha_mhz=ALPHA_MHZ, drag=True):
    alpha = alpha_rad_per_ns(alpha_mhz)
    ts = np.arange(T_MIN, T_MAX + DT / 2, DT)
    psi = np.array([1.0, 0.0, 0.0], dtype=complex)
    pops = []
    max_cons_err = 0.0
    for t in ts:
        h = hamiltonian(t, sigma, alpha, drag)

        def f(p):
            return -1j * h @ p

        k1 = f(psi)
        k2 = f(psi + DT / 2 * k1)
        k3 = f(psi + DT / 2 * k2)
        k4 = f(psi + DT * k3)
        psi = psi + DT / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        # Conservation is measured on the RAW step, BEFORE renormalisation,
        # so the check is not trivialised by the renormalisation itself.
        max_cons_err = max(max_cons_err, abs(float(np.linalg.norm(psi)) - 1.0))
        psi = psi / np.linalg.norm(psi)
        p = np.abs(psi) ** 2
        pops.append(p)
    return ts, np.array(pops), max_cons_err


def run_lindblad(sigma=SIGMA_NS, alpha_mhz=ALPHA_MHZ, drag=True):
    alpha = alpha_rad_per_ns(alpha_mhz)
    t1_ns, t2_ns = T1_US * 1000.0, T2_US * 1000.0
    tphi_ns = 1.0 / (1.0 / t2_ns - 1.0 / (2.0 * t1_ns))
    l_relax = np.sqrt(1.0 / t1_ns) * A
    l_phi = np.sqrt(1.0 / tphi_ns) * N_OP
    collapses = [l_relax, l_phi]
    ts = np.arange(T_MIN, T_MAX + DT / 2, DT)
    rho = np.zeros((3, 3), dtype=complex)
    rho[0, 0] = 1.0
    pops = []
    max_trace_err = 0.0
    for t in ts:
        h = hamiltonian(t, sigma, alpha, drag)

        def f(r):
            out = -1j * (h @ r - r @ h)
            for L in collapses:
                out += L @ r @ L.T.conj() - 0.5 * (L.T.conj() @ L @ r + r @ L.T.conj() @ L)
            return out

        k1 = f(rho)
        k2 = f(rho + DT / 2 * k1)
        k3 = f(rho + DT / 2 * k2)
        k4 = f(rho + DT * k3)
        rho = rho + DT / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        p = np.real(np.diag(rho))
        pops.append(p)
        max_trace_err = max(max_trace_err, abs(float(np.trace(rho).real) - 1.0))
    return ts, np.array(pops), max_trace_err, tphi_ns


def final_p2(sigma, alpha_mhz, drag, lindblad=False):
    if lindblad:
        _, pops, _, _ = run_lindblad(sigma, alpha_mhz, drag)
    else:
        _, pops, _ = run_unitary(sigma, alpha_mhz, drag)
    return float(pops[-1, 2]), float(pops[-1, 1]), float(pops[:, 2].max())


def main():
    wall_start = time.perf_counter()
    out = {
        "device": "3-level transmon |0>,|1>,|2>, rotating frame at omega_01",
        "alpha_MHz": ALPHA_MHZ,
        "alpha_rad_per_ns": alpha_rad_per_ns(ALPHA_MHZ),
        "sigma_ns": SIGMA_NS,
        "window_ns": [T_MIN, T_MAX],
        "dt_ns": DT,
        "omega0_rad_per_ns": float(np.pi / (SIGMA_NS * np.sqrt(2 * np.pi))),
        "omega0_MHz_cyclic": float(np.pi / (SIGMA_NS * np.sqrt(2 * np.pi)) / (2 * np.pi) * 1000),
        "drag_formula": "Q(t) = -dI/dt / alpha",
        "screenshot_comparison": (
            "Screenshot showed ~24.1% leakage over a 10 ns drive. "
            "That is a comparison point only, NOT a target and NOT reproduced. "
            "This run uses a 20 ns window and sigma=2 ns; see P2 values below."
        ),
        "legs": {},
        "sensitivity_unitary_final_P2": {},
    }

    # Main unitary legs
    for drag in (False, True):
        ts, pops, cons = run_unitary(drag=drag)
        key = "with_DRAG" if drag else "without_DRAG"
        out["legs"][key + "_unitary"] = {
            "final_P0": float(pops[-1, 0]),
            "final_P1_fidelity_to_|1>": float(pops[-1, 1]),
            "final_P2_leakage": float(pops[-1, 2]),
            "max_P2_during_drive": float(pops[:, 2].max()),
            "population_conservation_max_error": float(cons),
        }
        if drag:
            ts_out, pops_out = ts, pops
        else:
            ts_nodrag, pops_nodrag = ts, pops

    # Labelled decoherence leg
    for drag in (False, True):
        _, pops, trace_err, tphi = run_lindblad(drag=drag)
        key = "with_DRAG" if drag else "without_DRAG"
        out["legs"][key + "_lindblad_T1_T2"] = {
            "T1_us": T1_US, "T2_us": T2_US, "Tphi_us": float(tphi / 1000.0),
            "final_P0": float(pops[-1, 0]),
            "final_P1_fidelity_to_|1>": float(pops[-1, 1]),
            "final_P2_leakage": float(pops[-1, 2]),
            "max_P2_during_drive": float(pops[:, 2].max()),
            "trace_conservation_max_error": float(trace_err),
        }

    # Sensitivity (unitary, final P2)
    for alpha_mhz in (-200.0, -250.0, -300.0):
        for sigma in (1.5, 2.0, 3.0):
            p2_off, _, _ = final_p2(sigma, alpha_mhz, False)
            p2_on, _, _ = final_p2(sigma, alpha_mhz, True)
            out["sensitivity_unitary_final_P2"][f"alpha_{int(alpha_mhz)}MHz_sigma_{sigma}ns"] = {
                "without_DRAG": p2_off, "with_DRAG": p2_on
            }

    wall = time.perf_counter() - wall_start
    device_time_ns = T_MAX - T_MIN
    out["time_dilation"] = {
        "device_time_ns": device_time_ns,
        "wall_time_seconds_all_legs_and_sensitivity": wall,
        "note": (
            "Device time is nanoseconds; wall time is seconds of computer "
            "execution. The dynamics are dilated (magnified) to computer "
            "timescale; this is not real-time hardware execution and not "
            "a hardware speed claim."
        ),
    }
    out["not_verified"] = [
        "No real hardware was run.",
        "No hardware measurement was reproduced.",
        "No claim that this model equals any specific device, chip, or lab result.",
        "Decoherence rates T1/T2 are typical-order assumptions, stated above, not measured.",
        "DRAG here is first-order quadrature correction only; no detuning correction, no pulse-distortion or readout model.",
    ]

    with open("results.json", "w") as fh:
        json.dump(out, fh, indent=2)

    # Downsampled populations for both main unitary legs (every 0.2 ns)
    with open("populations.csv", "w") as fh:
        fh.write("t_ns,P0_noDRAG,P1_noDRAG,P2_noDRAG,P0_DRAG,P1_DRAG,P2_DRAG\n")
        step = int(0.2 / DT)
        for i in range(0, len(ts_nodrag), step):
            fh.write(
                f"{ts_nodrag[i]:.2f},{pops_nodrag[i,0]:.6f},{pops_nodrag[i,1]:.6f},"
                f"{pops_nodrag[i,2]:.6f},{pops_out[i,0]:.6f},{pops_out[i,1]:.6f},"
                f"{pops_out[i,2]:.6f}\n"
            )
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
