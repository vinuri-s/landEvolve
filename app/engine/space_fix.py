"""Corrected replacement for Landlab's SpaceLargeScaleEroder inner loop.

Landlab's compiled ``_sequential_ero_depo`` (landlab/components/space/ext/
calc_sequential_ero_depo.pyx) picks between two branches of a closed-form
soil-depth solution using an *exact* floating-point equality check:

    if (depo_rate == (K_sed[node_id] * Q_to_the_m[node_id] * slope_loc)):
        ... numerically safe formula ...
    else:
        ... formula with a genuine mathematical singularity as
            depo_rate -> sed_erosion_term ...

The `==` check is meant to detect that singular point, but only catches it
when the two floats are bit-for-bit identical. A node merely *very close* to
(not bit-identical to) that point -- which happens routinely on gently
sloping, near-graded terrain, where deposition rate naturally sits close to
erosion capacity -- takes the "unsafe" branch anyway and divides through
catastrophic floating-point cancellation, producing an enormous but finite
bogus elevation change (observed: up to ~1.7e11 m in one step on a real
production DEM). This is a confirmed upstream bug: still present unchanged
in Landlab's current GitHub master, and in the same fragile-numerics
neighbourhood as Landlab's own open, unfixed issue landlab/landlab#1901.

We can't safely patch Landlab's compiled .pyx/.so, so this module provides a
faithful, line-for-line reimplementation of the same algorithm -- identical
math, identical branches -- with three corrections, JIT-compiled with numba
so it stays close to the original's performance on multi-million-node grids
(a plain Python loop would not: this loop is inherently sequential along the
flow network, since each node's qs_in depends on every upstream node already
having been processed, so it can't be vectorized with ordinary numpy array
ops):

1. The exact `==` replaced with a direct check on the log's argument right
   before evaluating it (rather than a fixed tolerance on the inputs guessed
   in advance) -- see the near-singularity handling in the "normal" branch
   below for why.
2. `q` (discharge) floored at a tiny epsilon before any division by it --
   `depo_rate = v*qs_out/q` is a literal 0/0 -> NaN if a node has exactly
   zero discharge, which can happen at some boundary/edge configurations.
3. The argument to `exp()` clamped before evaluating -- `exp(H_loc/H_star)`
   overflows to `inf` once `H_loc/H_star` exceeds ~709 (IEEE double range).
   Landlab's own `thickness_lim` check (default 100 m) guards the start of
   each step, but with H_star as small as 0.5 that's still only 200
   H_star-units of headroom, and a single already-marginal step could push
   a node close enough to that boundary for the *next* step to overflow.

If numba isn't installed, ``patch_space_large_scale_eroder()`` is a no-op --
the engine falls back to Landlab's original (buggy but functional) code,
still protected by the statistical outlier guard in components.py.

Diagnostics: this module also counts how often each corrected pathway
actually fires, readable via ``get_and_reset_diag_counts()``, so future runs
report real telemetry instead of guessing.
"""

import numpy as np

try:
    import numba
    _HAVE_NUMBA = True
except ImportError:
    _HAVE_NUMBA = False

# Floor for the log's argument in the "normal" branch (see the near-
# singularity handling below): a first version of this fix pre-screened
# inputs with a fixed relative tolerance on (depo_rate - sed_erosion_term),
# guessed from a theoretical catastrophic-cancellation analysis. That proved
# too tight in practice (observed: a 53.8 m single-step jump at a 13-degree
# slope -- no physical explanation, and far outside what the guessed
# tolerance flagged). Checking the log's actual argument directly, right
# before evaluating it, is the more robust criterion: it catches the real
# danger regardless of what magnitude of input difference happens to trigger
# precision loss for a given set of values, instead of a single fixed
# tolerance guessed in advance.
_LOG_ARG_FLOOR = 1e-6

# Floor for discharge before dividing by it, and cap for the exp() argument
# (a very safe margin under the ~709 IEEE-double overflow point).
_Q_FLOOR = 1e-12
_EXP_ARG_CAP = 500.0

# diag_counts[0] = times the near-singularity branch fired
# diag_counts[1] = times the isinf() fallback fired
# diag_counts[2] = times the q-floor guard actually clamped a value
# diag_counts[3] = times the exp-overflow guard actually clamped a value
diag_counts = np.zeros(4, dtype=np.int64)

# Branch-tracking for nodes with an unusually large single-step |ΔH|: which
# code path produced it, so we can tell a legitimate depression-fill (the
# plain linear branch, triggered by slope <= 0 -- Landlab's own documented
# mechanism for filling a real local sink with actual deposition) apart from
# a still-unidentified numerical bug in the exp/log branches. Branch codes:
#   0 = linear, because H_loc > thickness_lim
#   1 = linear, because slope_loc <= 0            (genuine local depression)
#   2 = linear, because sed_erosion_loc == 0
#   3 = near-singular exp/log branch (the fix already applied)
#   4 = normal exp/log branch (not near-singular)
_DIAG_SAMPLE_THRESHOLD = 1.0  # metres; only record notably large steps
_DIAG_SAMPLE_CAP = 200
diag_sample_count = np.zeros(1, dtype=np.int64)
diag_sample_node = np.zeros(_DIAG_SAMPLE_CAP, dtype=np.int64)
diag_sample_branch = np.zeros(_DIAG_SAMPLE_CAP, dtype=np.int64)
diag_sample_delta = np.zeros(_DIAG_SAMPLE_CAP, dtype=np.float64)
diag_sample_slope = np.zeros(_DIAG_SAMPLE_CAP, dtype=np.float64)

_BRANCH_NAMES = {
    0: "linear (thickness_lim)",
    1: "linear (slope<=0, likely real depression fill)",
    2: "linear (sed_erosion==0)",
    3: "near_singular (our fix)",
    4: "normal exp/log",
}


def get_and_reset_diag_counts():
    global diag_counts
    counts = diag_counts.copy()
    diag_counts[:] = 0
    return {
        "near_singular": int(counts[0]),
        "isinf_fallback": int(counts[1]),
        "q_floored": int(counts[2]),
        "exp_capped": int(counts[3]),
    }


def get_and_reset_diag_samples(grid_ncols):
    """Return the recorded large-|ΔH| samples from the last step, decoded to
    (row, col, branch name, ΔH, slope), then reset the buffer."""
    global diag_sample_count
    n = int(diag_sample_count[0])
    n = min(n, _DIAG_SAMPLE_CAP)
    samples = []
    for i in range(n):
        node = int(diag_sample_node[i])
        samples.append({
            "row": node // grid_ncols,
            "col": node % grid_ncols,
            "branch": _BRANCH_NAMES.get(int(diag_sample_branch[i]), "unknown"),
            "delta_H": float(diag_sample_delta[i]),
            "slope": float(diag_sample_slope[i]),
        })
    diag_sample_count[0] = 0
    return samples


def _build_fixed_sequential_ero_depo():
    import math

    # counts is passed as an explicit parameter to the njit core (not
    # captured via closure): numba marks closure-captured numpy arrays
    # read-only by default, so mutating one in place inside the loop
    # (counts[i] += 1) fails to compile unless it arrives as a genuine
    # function argument instead.
    @numba.njit(cache=True)
    def _sequential_ero_depo_core(
        stack_flip_ud_sel, flow_receivers, cell_area, q, qs, qs_in,
        Es, Er, Q_to_the_m, slope, H, br,
        sed_erosion_term, bed_erosion_term, K_sed,
        ero_sed_effective, depo_effective,
        v, phi, F_f, H_star, dt, thickness_lim,
        counts,
        sample_count, sample_node, sample_branch, sample_delta, sample_slope,
    ):
        vol_SSY_riv = 0.0

        for idx in range(stack_flip_ud_sel.shape[0]):
            node_id = stack_flip_ud_sel[idx]

            q_node = q[node_id]
            if q_node < _Q_FLOOR:
                q_node = _Q_FLOOR
                counts[2] += 1

            qs_out = (
                qs_in[node_id]
                + Es[node_id] * cell_area[node_id]
                + (1.0 - F_f) * Er[node_id] * cell_area[node_id]
            ) / (1.0 + (v * cell_area[node_id] / q_node))

            depo_rate = v * qs_out / q_node
            H_loc = H[node_id]
            H_Before = H[node_id]
            slope_loc = slope[node_id]
            sed_erosion_loc = sed_erosion_term[node_id]
            bed_erosion_loc = bed_erosion_term[node_id]
            branch_code = 4

            if H_loc > thickness_lim or slope_loc <= 0 or sed_erosion_loc == 0:
                if H_loc > thickness_lim:
                    branch_code = 0
                elif slope_loc <= 0:
                    branch_code = 1
                else:
                    branch_code = 2
                H_loc += (depo_rate / (1 - phi) - sed_erosion_loc / (1 - phi)) * dt
            else:
                # ratio is the formula's true singular quantity (depo_rate ==
                # sed_erosion_loc, i.e. ratio == 1) -- note this is NOT
                # necessarily the same as Landlab's own `depo_rate ==
                # K_sed*Q^m*slope` equality check: those only coincide when
                # sp_crit_sed == 0. Basing the safety check on the formula's
                # actual denominator (sed_erosion_loc) is correct in general.
                ratio = depo_rate / sed_erosion_loc
                A = ratio - 1.0

                exp_arg1 = (
                    depo_rate / (1 - phi) - (sed_erosion_loc / (1 - phi))
                ) * (dt / H_star)
                exp_arg2 = H_loc / H_star
                capped = False
                if exp_arg1 > _EXP_ARG_CAP:
                    exp_arg1 = _EXP_ARG_CAP
                    capped = True
                if exp_arg2 > _EXP_ARG_CAP:
                    exp_arg2 = _EXP_ARG_CAP
                    capped = True

                # Rather than guessing in advance how close A must be to zero
                # before catastrophic cancellation becomes dangerous (a fixed
                # tolerance on the inputs proved too tight for at least one
                # real case: a 53.8 m single-step jump at a 13 degree slope,
                # nowhere near what a fixed 1e-4 tolerance on A would have
                # flagged), directly evaluate the actual quantity that's
                # dangerous -- the log's argument -- and check *that* for
                # being suspiciously close to zero or negative. This targets
                # the real numerical danger regardless of what magnitude of A
                # happens to trigger precision loss for these specific input
                # values.
                use_safe = abs(A) < 1e-300  # guard literal 1/0 before it happens
                log_arg = 0.0
                if not use_safe:
                    B = math.exp(exp_arg1)
                    C = A * math.exp(exp_arg2) + 1.0
                    log_arg = (1.0 / A) * (B * C - 1.0)
                    use_safe = log_arg <= _LOG_ARG_FLOOR

                if use_safe:
                    counts[0] += 1
                    branch_code = 3
                    # Numerically safe branch (Landlab's "blowup" case) --
                    # the correct closed-form limit as ratio -> 1.
                    arg = ((sed_erosion_loc / (1 - phi)) / H_star) * dt
                    H_loc = H_loc * math.log(arg + math.exp(exp_arg2))
                else:
                    if capped:
                        counts[3] += 1
                    H_loc = H_star * math.log(log_arg)
                if math.isinf(H_loc) or math.isnan(H_loc):
                    counts[1] += 1
                    H_loc = (
                        H[node_id]
                        + (depo_rate / (1 - phi) - sed_erosion_loc / (1 - phi)) * dt
                    )

            H_loc = max(0.0, H_loc)
            ero_bed = bed_erosion_loc * math.exp(-min(H_loc / H_star, _EXP_ARG_CAP))

            qs_out_adj = (
                qs_in[node_id]
                - ((H_loc - H_Before) * (1 - phi) * cell_area[node_id] / dt)
                + (1.0 - F_f) * ero_bed * cell_area[node_id]
            )

            qs[node_id] = qs_out_adj
            qs_in[flow_receivers[node_id]] += qs[node_id]

            H[node_id] = H_loc
            br[node_id] += -dt * ero_bed
            vol_SSY_riv += F_f * ero_bed * cell_area[node_id]

            Hd = H_loc - H_Before
            depo_effective[node_id] = (v * qs_out_adj / q_node) / (1 - phi)
            depo_effective[node_id] = max(depo_effective[node_id], Hd / dt)
            ero_sed_effective[node_id] = depo_effective[node_id] - Hd / dt

            if abs(Hd) > _DIAG_SAMPLE_THRESHOLD:
                slot = sample_count[0]
                if slot < sample_node.shape[0]:
                    sample_node[slot] = node_id
                    sample_branch[slot] = branch_code
                    sample_delta[slot] = Hd
                    sample_slope[slot] = slope_loc
                    sample_count[0] = slot + 1

        return vol_SSY_riv

    def _sequential_ero_depo_fixed(
        stack_flip_ud_sel, flow_receivers, cell_area, q, qs, qs_in,
        Es, Er, Q_to_the_m, slope, H, br,
        sed_erosion_term, bed_erosion_term, K_sed,
        ero_sed_effective, depo_effective,
        v, phi, F_f, H_star, dt, thickness_lim,
    ):
        # Thin wrapper matching Landlab's exact expected signature (this is
        # what actually replaces landlab's _sequential_ero_depo); forwards
        # the module-level diagnostic arrays to the njit core as real
        # arguments so numba treats them as writable.
        return _sequential_ero_depo_core(
            stack_flip_ud_sel, flow_receivers, cell_area, q, qs, qs_in,
            Es, Er, Q_to_the_m, slope, H, br,
            sed_erosion_term, bed_erosion_term, K_sed,
            ero_sed_effective, depo_effective,
            v, phi, F_f, H_star, dt, thickness_lim,
            diag_counts,
            diag_sample_count, diag_sample_node, diag_sample_branch,
            diag_sample_delta, diag_sample_slope,
        )

    return _sequential_ero_depo_fixed


_patched = False


def patch_space_large_scale_eroder():
    """Replace Landlab's buggy compiled inner loop with our corrected,
    numba-compiled equivalent. Safe to call more than once; no-op if numba
    isn't installed (the engine falls back to the outlier guard only)."""
    global _patched
    if _patched or not _HAVE_NUMBA:
        return _HAVE_NUMBA

    fixed_fn = _build_fixed_sequential_ero_depo()

    import landlab.components.space.space_large_scale_eroder as _sle_mod
    _sle_mod._sequential_ero_depo = fixed_fn

    _patched = True
    return True
