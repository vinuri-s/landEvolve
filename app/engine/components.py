import abc
import inspect
import json
import os
import numpy as np
import ast

from landlab.components import (
    FlowAccumulator,
    LakeMapperBarnes,
    Space,
    SpaceLargeScaleEroder,
    DepthDependentDiffuser,
    LithoLayers,
)


# =========================================================
# BASE
# =========================================================

class SimulationComponent(abc.ABC):

    def __init__(self, grid):
        self.grid = grid

    @abc.abstractmethod
    def run(self, dt: float):
        pass

    def _add_field_if_missing(self, name, value, at="node"):
        if name not in self.grid[at]:
            self.grid.add_field(name, value, at=at)


# =========================================================
# TECTONICS
# =========================================================

class TectonicsComponent(SimulationComponent):
    """
    Applies rock uplift to the landscape each step, the tectonic forcing that
    competes with erosion to build relief. Landlab has no dedicated uplift
    component — the idiomatic approach is to add ``uplift_rate * dt`` to the
    elevation field — so this is custom logic, consistent with how the rest of
    the engine is structured.

    Two modes (long-term forcing):

    * **Uniform** — constant block uplift: every core node rises at
                    ``uplift_rate`` (length/time).
    * **Spatial** — per-node uplift rate from a raster (resampled to the grid),
                    for differential / tilted uplift across the domain.

    Correctness details:

    * Only **core nodes** are uplifted; boundary/outlet nodes stay fixed as base
      level, so relief actually grows (uplifting everything just raises base
      level).
    * When a bedrock field exists (SPACE / diffuser), **both
      ``bedrock__elevation`` and ``topographic__elevation`` are raised** by
      ``uplift_rate * dt``, since ``topographic = bedrock + soil`` — uplifting
      only the surface would corrupt the soil/bedrock budget.

    Runs near the **end** of each step (after erosion), following the standard
    landlab SPACE convention (erode, then uplift).
    """

    def __init__(self, grid, **params):
        super().__init__(grid)

        self.mode = str(params.get("mode", "Uniform")).strip()
        self.uplift_rate = float(params.get("uplift_rate", 0.0))

        n = grid.number_of_nodes
        if self.mode == "Spatial":
            self._rate_field = self._load_raster(grid, params.get("uplift_raster"))
        else:
            self._rate_field = np.full(n, self.uplift_rate, dtype=float)

    def _load_raster(self, grid, path):
        n = grid.number_of_nodes
        if not path or not os.path.exists(path):
            print("TectonicsComponent: uplift raster not found; using uniform uplift rate.")
            return np.full(n, self.uplift_rate, dtype=float)
        try:
            import rasterio
            from rasterio.enums import Resampling
            with rasterio.open(path) as src:
                data = src.read(1, out_shape=grid.shape, resampling=Resampling.bilinear).astype(float)
                if src.nodata is not None:
                    data[data == src.nodata] = np.nan
            flat = data.flatten()
            if np.isnan(flat).any():
                mean = np.nanmean(flat)
                flat = np.where(np.isnan(flat), mean if np.isfinite(mean) else self.uplift_rate, flat)
            return flat
        except Exception as e:
            print(f"TectonicsComponent: uplift raster load failed ({e}); using uniform uplift.")
            return np.full(n, self.uplift_rate, dtype=float)

    def run(self, dt):
        if dt <= 0:
            return
        core = self.grid.core_nodes
        du = self._rate_field[core] * dt
        self.grid.at_node["topographic__elevation"][core] += du
        # Keep the rock column consistent with the surface for the SPACE budget.
        if "bedrock__elevation" in self.grid.at_node:
            self.grid.at_node["bedrock__elevation"][core] += du

        # Accumulate total applied uplift so the post-run difference map can be
        # corrected (final - initial - uplift = the geomorphic erosion signal).
        if not hasattr(self.grid, "_cumulative_uplift"):
            self.grid._cumulative_uplift = np.zeros(self.grid.number_of_nodes, dtype=float)
        self.grid._cumulative_uplift[core] += du


# =========================================================
# PRECIPITATION
# =========================================================

class PrecipitationComponent(SimulationComponent):
    """
    Sets the runoff field (`water__unit_flux_in`) that FlowAccumulator converts
    to `surface_water__discharge`, so climate controls erosion. This is the
    clean, physically-correct insertion point: it writes the *base* runoff each
    step (before FlowAccumulator routes it), and any vegetation runoff
    multiplier composes on top.

    The modes are chosen for the **long-term** nature of these simulations
    (dt of years-to-millennia, far larger than individual storms), so they
    represent *effective* climate forcing rather than sub-timestep storms:

    * **Uniform**    — constant effective precipitation over the whole grid
                       (the standard LEM baseline).
    * **Spatial**    — per-node effective precipitation from a (mean-annual)
                       rainfall raster, resampled to the grid: orographic /
                       spatial gradients, constant in time.
    * **Stochastic** — inter-period climate variability: each timestep draws a
                       mean precipitation from a gamma distribution (mean =
                       `precipitation`, coefficient of variation = `variability`),
                       producing wet/dry periods that drive episodic erosion.
                       (Aggregating sub-storm events is meaningless when
                       dt >> storm scale — it averages out — so we model
                       variability at the timestep scale instead.)
    * **Trend**      — deterministic climate change: precipitation varies
                       linearly from `precipitation` to `final_precipitation`
                       over the simulation (e.g. progressive drying/wetting).

    Effective runoff = precipitation x runoff_coefficient, in the same units as
    FlowAccumulator's `runoff_rate` (default 1.0 reproduces prior behaviour),
    so existing K_sed/K_br calibration stays valid.
    """

    def __init__(self, grid, **params):
        super().__init__(grid)

        self.mode = str(params.get("mode", "Uniform")).strip()
        self.precip = float(params.get("precipitation", 1.0))
        self.coeff = float(params.get("runoff_coefficient", 1.0))
        self.final_precip = float(params.get("final_precipitation", self.precip))
        self.variability = float(params.get("variability", 0.0))
        # Injected by the runner so Trend mode knows the full simulation length.
        self.total_time = float(params.get("total_time", 0.0))
        self._elapsed = 0.0

        seed = params.get("random_seed", None)
        try:
            self._rng = np.random.default_rng(int(seed)) if seed not in (None, "", 0, "0") else np.random.default_rng()
        except (ValueError, TypeError):
            self._rng = np.random.default_rng()

        if "water__unit_flux_in" not in grid.at_node:
            grid.add_ones("water__unit_flux_in", at="node")

        # Static per-node spatial field (Spatial mode only); other modes are
        # spatially uniform and computed per step.
        self._spatial = self._load_raster(grid, params.get("precipitation_raster")) \
            if self.mode == "Spatial" else None

        self._apply(self._field_for_now())

    def _apply(self, field):
        # `_base_runoff` is the climate signal the vegetation multiplier rides on.
        self.grid._base_runoff = np.array(field, dtype=float)
        self.grid.at_node["water__unit_flux_in"][:] = field

    def _field_for_now(self):
        """Per-node runoff field for the current simulation state."""
        n = self.grid.number_of_nodes
        if self.mode == "Spatial":
            return self._spatial * self.coeff

        if self.mode == "Trend":
            frac = min(self._elapsed / self.total_time, 1.0) if self.total_time > 0 else 0.0
            rate = self.precip + (self.final_precip - self.precip) * frac
        elif self.mode == "Stochastic":
            rate = self._stochastic_rate()
        else:  # Uniform
            rate = self.precip

        return np.full(n, max(rate, 0.0) * self.coeff, dtype=float)

    def _stochastic_rate(self):
        """Draw a timestep mean precipitation from a gamma distribution with the
        given mean and coefficient of variation (gamma keeps it non-negative)."""
        cv = self.variability
        if cv <= 0 or self.precip <= 0:
            return self.precip
        shape = 1.0 / (cv * cv)
        scale = self.precip * cv * cv
        return float(self._rng.gamma(shape, scale))

    def _load_raster(self, grid, path):
        n = grid.number_of_nodes
        if not path or not os.path.exists(path):
            print("PrecipitationComponent: raster not found; using uniform precipitation value.")
            return np.full(n, self.precip, dtype=float)
        try:
            import rasterio
            from rasterio.enums import Resampling
            with rasterio.open(path) as src:
                data = src.read(1, out_shape=grid.shape, resampling=Resampling.bilinear).astype(float)
                if src.nodata is not None:
                    data[data == src.nodata] = np.nan
            flat = data.flatten()
            if np.isnan(flat).any():
                mean = np.nanmean(flat)
                flat = np.where(np.isnan(flat), mean if np.isfinite(mean) else self.precip, flat)
            return flat
        except Exception as e:
            print(f"PrecipitationComponent: raster load failed ({e}); using uniform precipitation.")
            return np.full(n, self.precip, dtype=float)

    def run(self, dt):
        self._elapsed += dt
        self._apply(self._field_for_now())


# =========================================================
# BASE SPACE
# =========================================================

class BaseSpaceComponent(SimulationComponent):

    def _clip_soil(self):
        np.clip(
            self.grid.at_node["soil__depth"],
            0,
            None,
            out=self.grid.at_node["soil__depth"],
        )

    def _ensure_fields(self, soil_depth=1.0):

        if "soil__depth" not in self.grid.at_node:
            self._add_field_if_missing(
                "soil__depth",
                np.full(self.grid.number_of_nodes, soil_depth),
                at="node"
            )

        if "bedrock__elevation" not in self.grid.at_node:
            self.grid.at_node["bedrock__elevation"] = (
                self.grid.at_node["topographic__elevation"]
                - self.grid.at_node["soil__depth"]
            )

    def _apply_vegetation(self, K_br, K_sed):
        if not hasattr(self.grid, '_veg_K_br_mult'):
            return K_br, K_sed

        n = self.grid.number_of_nodes

        if isinstance(K_br, np.ndarray):
            K_br_eff = K_br.copy()
        else:
            K_br_eff = np.full(n, float(K_br))

        if isinstance(K_sed, np.ndarray):
            K_sed_eff = K_sed.copy()
        else:
            K_sed_eff = np.full(n, float(K_sed))

        K_br_eff *= self.grid._veg_K_br_mult
        K_sed_eff *= self.grid._veg_K_sed_mult

        return K_br_eff, K_sed_eff


def _apply_litho_veg_to_space(comp):
    """
    Combine lithology (per-node bedrock erodibility) and vegetation
    multipliers, then push the effective K_sed / K_br into the wrapped
    Landlab eroder for this timestep.

    - Bedrock erodibility K_br is driven by lithology (grid 'K_sp' field,
      maintained in-place by LithoLayers) when present, else the scalar
      user param.
    - Sediment erodibility K_sed is derived from K_br using the user's
      configured K_sed:K_br ratio, so the modeller's intended relationship
      is preserved instead of a hard-coded factor.
    - Vegetation multipliers (if any) are applied on top, per node.

    If neither lithology nor vegetation is active, the eroder's own
    initialised K arrays are left untouched.
    """
    grid = comp.grid
    has_litho = "K_sp" in grid.at_node
    has_veg = hasattr(grid, "_veg_K_br_mult")

    if not (has_litho or has_veg):
        return

    if has_litho:
        K_br_base = grid.at_node["K_sp"]
        ratio = (comp._base_K_sed / comp._base_K_br) if comp._base_K_br else 1.0
        K_sed_base = K_br_base * ratio
    else:
        K_br_base = comp._base_K_br
        K_sed_base = comp._base_K_sed

    K_br, K_sed = comp._apply_vegetation(K_br_base, K_sed_base)
    comp.space._K_br = K_br
    comp.space._K_sed = K_sed


# =========================================================
# VEGETATION
# =========================================================

class VegetationComponent(SimulationComponent):
    """
    Class-based vegetation component supporting static and scheduled-transition modes.

    vegetation_classes: dict {int class_id: {name, K_sed_multiplier, K_br_multiplier,
                                              linear_diffusivity_multiplier, runoff_multiplier}}
    vegetation_mode: 'Static' | 'Transition'
    static_class_id: int  (initial class for Static mode; fallback in Transition mode
                           when no transitions are defined)
    transitions: list of {source_class_id, target_class_id, timestep}  (Transition mode only).
                 The grid is initialised to the source class of the earliest transition.
                 All nodes carrying source_class_id flip to target_class_id at the given timestep.
    """

    def __init__(self, grid, vegetation_classes, **kwargs):
        super().__init__(grid)

        self.mode = kwargs.get('vegetation_mode', 'Static')
        self.classes = {int(k): v for k, v in vegetation_classes.items()}

        default_class_id = next(iter(self.classes), 0)
        self.static_class_id = int(kwargs.get('static_class_id', default_class_id))

        transitions_raw = kwargs.get('transitions', [])
        if isinstance(transitions_raw, str):
            try:
                transitions_raw = json.loads(transitions_raw)
            except (json.JSONDecodeError, TypeError):
                transitions_raw = []
        self.transitions = [
            {
                'source_class_id': int(t.get('source_class_id', 0)),
                'target_class_id': int(t.get('target_class_id', 0)),
                'timestep': int(t.get('timestep', 0)),
            }
            for t in transitions_raw
        ]

        self.current_timestep = 0

        n = grid.number_of_nodes
        # In Transition mode the grid starts with the source class of the
        # earliest-scheduled transition (not static_class_id, which is unused
        # in this mode and often left at a default that doesn't match).
        if self.mode == 'Transition' and self.transitions:
            earliest = min(self.transitions, key=lambda t: t['timestep'])
            initial_class_id = earliest['source_class_id']
        else:
            initial_class_id = self.static_class_id
        grid._veg_class_grid = np.full(n, initial_class_id, dtype=int)

        grid._veg_K_sed_mult = np.ones(n)
        grid._veg_K_br_mult = np.ones(n)
        grid._veg_D_mult = np.ones(n)

        if "water__unit_flux_in" in grid.at_node:
            grid._base_runoff = np.array(grid.at_node["water__unit_flux_in"], dtype=float)
        else:
            grid._base_runoff = np.ones(n, dtype=float)

        self._update_multipliers()

    def _update_multipliers(self):
        veg_grid = self.grid._veg_class_grid
        n = len(veg_grid)

        K_sed = np.ones(n)
        K_br = np.ones(n)
        D = np.ones(n)
        runoff = np.ones(n)

        for cls_id, cls_params in self.classes.items():
            mask = veg_grid == cls_id
            if mask.any():
                K_sed[mask] = cls_params.get('K_sed_multiplier', 1.0)
                K_br[mask] = cls_params.get('K_br_multiplier', 1.0)
                D[mask] = cls_params.get('linear_diffusivity_multiplier', 1.0)
                runoff[mask] = cls_params.get('runoff_multiplier', 1.0)

        self.grid._veg_K_sed_mult = K_sed
        self.grid._veg_K_br_mult = K_br
        self.grid._veg_D_mult = D

        if "water__unit_flux_in" in self.grid.at_node:
            new_runoff = (self.grid._base_runoff * runoff).copy()
            self.grid.at_node["water__unit_flux_in"] = new_runoff

    def run(self, dt):
        self.current_timestep += 1

        # On the first step, re-apply multipliers unconditionally so that
        # water__unit_flux_in — which FlowAccumulator adds after this component
        # is constructed — receives the correct runoff scaling in both modes.
        if self.current_timestep == 1:
            self._update_multipliers()

        if self.mode == 'Transition':
            changed = False
            for t in self.transitions:
                if t['timestep'] == self.current_timestep:
                    src = t['source_class_id']
                    tgt = t['target_class_id']
                    mask = self.grid._veg_class_grid == src
                    if mask.any():
                        self.grid._veg_class_grid[mask] = tgt
                        changed = True
            if changed:
                self._update_multipliers()

        # Re-apply the runoff multiplier every step so it composes with a
        # (possibly time-varying) precipitation base set just before this runs.
        if "water__unit_flux_in" in self.grid.at_node:
            self._update_multipliers()


# =========================================================
# LITHOLOGY
# =========================================================

class LithoLayersComponent(SimulationComponent):
    """
    Wraps Landlab's LithoLayers with MaterialLayers mode.

    z0s  — cumulative positive depths (m) from surface to the bottom of each
            layer, ordered surface-to-base.  E.g. [10, 30] means the top layer
            occupies 0-10 m and the second layer occupies 10-30 m.
    ids  — rock-type ID for each layer (same order as z0s).
    attrs — {'K_sp': {id: value, ...}}  (and optionally other properties).

    After each run_one_step() the K_sp field on the grid is refreshed so
    SpaceComponent always reads the currently exposed rock's erodibility.
    """

    def __init__(self, grid, **params):
        super().__init__(grid)

        def safe(v):
            if isinstance(v, str):
                return ast.literal_eval(v)
            return v

        z0s  = list(safe(params["z0s"]))
        ids  = list(safe(params["ids"]))
        attrs = safe(params["attrs"])

        x0 = float(params.get("x0", 0.0))
        y0 = float(params.get("y0", 0.0))

        # LithoLayers automatically creates and maintains grid.at_node["K_sp"]
        # IN-PLACE.  We must not reassign that field anywhere, or downstream
        # components holding a reference to it would go stale.
        self.lith = LithoLayers(
            grid, z0s, ids, attrs,
            x0=x0, y0=y0,
            layer_type="MaterialLayers",
            rock_id=ids[-1],   # deposited material uses the base rock type
        )

    def run(self, dt):
        # Updates grid.at_node["K_sp"] in-place to the currently exposed rock.
        self.lith.run_one_step()


# =========================================================
# SPACE
# =========================================================

class SpaceComponent(BaseSpaceComponent):

    def __init__(self, grid, **params):
        super().__init__(grid)

        self._ensure_fields(params.get("soil_depth", 1.0))

        valid = inspect.signature(Space.__init__).parameters
        safe_params = {k: v for k, v in params.items() if k in valid}

        self.space = Space(grid, **safe_params)

        # Store base erodibility for lithology/vegetation scaling each step.
        # These are the user-configured values before any modifier is applied.
        self._base_K_br = float(params.get("K_br", 1e-5))
        self._base_K_sed = float(params.get("K_sed", 1e-3))

    def run(self, dt):
        self._clip_soil()
        _apply_litho_veg_to_space(self)
        self.space.run_one_step(dt)


# =========================================================
# SPACE LARGE SCALE
# =========================================================

class SpaceLargeScaleEroderComponent(BaseSpaceComponent):

    def __init__(self, grid, **params):
        super().__init__(grid)

        self._ensure_fields(params.get("soil_depth", 1.0))

        valid = inspect.signature(SpaceLargeScaleEroder.__init__).parameters
        safe_params = {k: v for k, v in params.items() if k in valid}

        self.space = SpaceLargeScaleEroder(grid, **safe_params)

        self._base_K_br = float(params.get("K_br", 1e-5))
        self._base_K_sed = float(params.get("K_sed", 1e-3))

    def run(self, dt):
        self._clip_soil()
        _apply_litho_veg_to_space(self)
        self.space.run_one_step(dt)


# =========================================================
# FLOW (FIXED)
# =========================================================

class FlowAccumulatorComponent(SimulationComponent):

    def __init__(self, grid, **params):
        super().__init__(grid)

        # 🚨 CRITICAL FIX: strip ALL non-landlab args
        for bad in ["erodibility_map", "lithology_type", "geology_file"]:
            params.pop(bad, None)

        if "water__unit_flux_in" not in grid.at_node:
            grid.add_ones("water__unit_flux_in", at="node")

        self.flow = FlowAccumulator(grid, **params)

        # Depression handling. FlowDirectorSteepest/D8 alone dead-ends flow in
        # internal pits, so SPACE dumps the whole upstream sediment load into the
        # sink — the runaway multi-thousand-metre "deposition" spike. LakeMapperBarnes
        # (Barnes priority-flood, pure-landlab/Cython — no richdem) reroutes flow
        # across depressions each step in near-linear time.
        #
        # Crucially it fills a SCRATCH surface (`_depression_fill__surface`), not
        # `topographic__elevation`, so the rerouting never injects fake sediment
        # into the terrain that SPACE erodes.
        if "_depression_fill__surface" not in grid.at_node:
            grid.add_zeros("_depression_fill__surface", at="node")

        director = str(params.get("flow_director", "")).lower()
        method = "D8" if "d8" in director else "Steepest"
        self.lake_mapper = LakeMapperBarnes(
            grid,
            method=method,
            surface="topographic__elevation",
            fill_surface="_depression_fill__surface",
            fill_flat=False,
            redirect_flow_steepest_descent=True,
            reaccumulate_flow=True,
        )

    def run(self, dt):
        self.flow.run_one_step()
        self.lake_mapper.run_one_step()


# =========================================================
# DIFFUSER
# =========================================================

class DepthDependentDiffuserComponent(SimulationComponent):

    def __init__(self, grid, **params):
        super().__init__(grid)

        if "soil__depth" not in grid.at_node:
            grid.add_ones("soil__depth", at="node")

        if "soil_production__rate" not in grid.at_node:
            grid.add_zeros("soil_production__rate", at="node")

        if "bedrock__elevation" not in grid.at_node:
            grid.add_field(
                "bedrock__elevation",
                grid.at_node["topographic__elevation"].copy() - grid.at_node["soil__depth"].copy(),
                at="node",
            )

        self._base_kd = float(params.get("linear_diffusivity", 1.0))
        self.diff = DepthDependentDiffuser(grid, **params)

    def run(self, dt):
        # DepthDependentDiffuser stores its diffusivity as a scalar in `_K`
        # (used per-link in soilflux). Vegetation cover reduces hillslope
        # transport; since _K is scalar we apply the mean cover multiplier.
        if hasattr(self.grid, '_veg_D_mult'):
            mean_mult = float(np.mean(self.grid._veg_D_mult))
            self.diff._K = self._base_kd * mean_mult
        self.diff.run_one_step(dt)