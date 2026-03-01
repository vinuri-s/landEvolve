"""
LandEvolve Core Engine Module

Exposes the primary API for running landscape evolution simulations 
and generating visualization artifacts, hiding internal component logic.
"""

from .runner import run_simulation, SimulationRunner
from .components import SimulationComponent
from .visualization import generate_3d_comparison_html

__all__ = [
    "run_simulation",
    "SimulationRunner",
    "SimulationComponent",
    "generate_3d_comparison_html"
]