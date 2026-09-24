# EFEL (vendored)

Copy of **EFEL 1.0** (with the one small patch listed below) — Elastic Fault, Earthquake and Landslide
components for Landlab, by Adam M. Forte (Louisiana State University).

* Source: https://github.com/amforte/elastic_fault_earthquake_and_landslide
* License: MIT (see `LICENSE` in this folder)
* Requires the compiled `okada4py` package (Jolivet, https://github.com/jolivetr/okada4py)
  for `DippingFault`, `VerticalFault` and `EarthquakeSequence`.

## Local patches

* `eq_generator.py`, `EarthquakeSequence.plot_ruptures` (vertical-fault branch):
  moved `ax1.set_title(...)` below the line that creates `ax1`. As shipped it raised
  `UnboundLocalError` for every `VerticalFault`. (Worth reporting upstream.)

LandEvolve wraps these classes in `app/engine/tectonics.py`
(`FaultComponent`, `EarthquakeComponent`, `LandslideComponent`). Avoid editing
the files here; when updating from upstream, re-apply the patch above.

Please cite: A.M. Forte, *EFEL 1.0: An integrated set of components for Landlab to
simulate landscape evolution from fault creep, earthquakes, and coseismic landslides*,
Geosci. Model Dev. (in review).
