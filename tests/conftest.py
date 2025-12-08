# tests/conftest.py
"""Pytest configuration and fixtures for sensitivity analysis tests"""

import pytest
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from PyQt6.QtWidgets import QApplication
from db.db_session import DatabaseSession

@pytest.fixture(scope="session")
def qapp():
    """Create QApplication instance for all tests"""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app
    # Don't quit here - let pytest handle it

@pytest.fixture(scope="session")
def db_session():
    """Create database session for tests"""
    db = DatabaseSession()
    session = db.get_session()
    yield session
    session.close()

@pytest.fixture
def test_dem_path():
    """Path to test DEM file"""
    return "resources/inputs/whiriapa/whiriapa_1m.tif"

@pytest.fixture
def base_simulation_params():
    """Base simulation parameters"""
    return {
        'simulation_period': 1000,
        'time_step': 10,
        'location': 'Whiria Pa',
        'resolution': '1m'
    }

@pytest.fixture
def kbr_test_values():
    """K_br values for sensitivity testing"""
    return [
        1e-7,    # Default
        1e-6,
        1e-5,
    ]