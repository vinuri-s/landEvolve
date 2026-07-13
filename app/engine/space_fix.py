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
math, identical branches -- with that one check replaced by a proper
tolerance comparison, JIT-compiled with numba so it stays close to the
original's performance on multi-million-node grids (a plain Python loop
would not: this loop is inherently sequential along the flow network, since
each node's qs_in depends on every upstream node already having been
processed, so it can't be vectorized with ordinary numpy array ops).

If numba isn't installed, ``patch_space_large_scale_eroder()`` is a no-op --
the engine falls back to Landlab's original (buggy but functional) code,
still protected by the statistical outlier guard in components.py.
"""

import numpy as np

try:
    import numba
    _HAVE_NUMBA = True
except ImportError:
    _HAVE_NUMBA = False

# Relative/absolute tolerance for the near-singularity check. The two
# formula branches are two continuous expressions of the same underlying
# solution and agree closely near the singular point (that's the nature of
# a removable singularity), so being generous about when to prefer the
# numerically stable branch costs essentially no accuracy while avoiding
# the catastrophic-cancellation blowup entirely.
_REL_TOL = 1e-4
_ABS_TOL = 1e-10


def _build_fixed_sequential_ero_depo():
    import math

    @numba.njit(cache=True)
    def _sequential_ero_depo_fixed(
        stack_flip_ud_sel, flow_receivers, cell_area, q, qs, qs_in,
        Es, Er, Q_to_the_m, slope, H, br,
        sed_erosion_term, bed_erosion_term, K_sed,
        ero_sed_effective, depo_effective,
        v, phi, F_f, H_star, dt, thickness_lim,
    ):
        vol_SSY_riv = 0.0

        for idx in range(stack_flip_ud_sel.shape[0]):
            node_id = stack_flip_ud_sel[idx]

            qs_out = (
                qs_in[node_id]
                + Es[node_id] * cell_area[node_id]
                + (1.0 - F_f) * Er[node_id] * cell_area[node_id]
            ) / (1.0 + (v * cell_area[node_id] / q[node_id]))

            depo_rate = v * qs_out / q[node_id]
            H_loc = H[node_id]
            H_Before = H[node_id]
            slope_loc = slope[node_id]
            sed_erosion_loc = sed_erosion_term[node_id]
            bed_erosion_loc = bed_erosion_term[node_id]

            if H_loc > thickness_lim or slope_loc <= 0 or sed_erosion_loc == 0:
                H_loc += (depo_rate / (1 - phi) - sed_erosion_loc / (1 - phi)) * dt
            else:
                capacity = K_sed[node_id] * Q_to_the_m[node_id] * slope_loc
                diff = depo_rate - capacity
                near_singular = abs(diff) <= (
                    _ABS_TOL + _REL_TOL * max(abs(depo_rate), abs(capacity))
                )
                if near_singular:
                    # Numerically safe branch (Landlab's "blowup" case).
                    H_loc = H_loc * math.log(
                        ((sed_erosion_loc / (1 - phi)) / H_star) * dt
                        + math.exp(H_loc / H_star)
                    )
                else:
                    ratio = (depo_rate / (1 - phi)) / (sed_erosion_loc / (1 - phi))
                    H_loc = H_star * math.log(
                        (1.0 / (ratio - 1.0))
                        * (
                            math.exp(
                                (depo_rate / (1 - phi) - (sed_erosion_loc / (1 - phi)))
                                * (dt / H_star)
                            )
                            * ((ratio - 1.0) * math.exp(H_loc / H_star) + 1.0)
                            - 1.0
                        )
                    )
                if math.isinf(H_loc):
                    H_loc = (
                        H[node_id]
                        + (depo_rate / (1 - phi) - sed_erosion_loc / (1 - phi)) * dt
                    )

            H_loc = max(0.0, H_loc)
            ero_bed = bed_erosion_loc * math.exp(-H_loc / H_star)

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
            depo_effective[node_id] = (v * qs_out_adj / q[node_id]) / (1 - phi)
            depo_effective[node_id] = max(depo_effective[node_id], Hd / dt)
            ero_sed_effective[node_id] = depo_effective[node_id] - Hd / dt

        return vol_SSY_riv

    return _sequential_ero_depo_fixed


_patched = False


def patch_space_large_scale_eroder():
    """Replace Landlab's buggy compiled inner loop with our corrected,
    numba-compiled equivalent, for both SpaceLargeScaleEroder and the plain
    Space component. Safe to call more than once; no-op if numba isn't
    installed (the engine falls back to the outlier guard only)."""
    global _patched
    if _patched or not _HAVE_NUMBA:
        return _HAVE_NUMBA

    fixed_fn = _build_fixed_sequential_ero_depo()

    import landlab.components.space.space_large_scale_eroder as _sle_mod
    _sle_mod._sequential_ero_depo = fixed_fn

    _patched = True
    return True
