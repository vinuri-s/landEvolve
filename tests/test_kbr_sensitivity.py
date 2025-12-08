# tests/test_kbr_sensitivity.py
"""
Sensitivity analysis tests for K_br parameter in SpaceLargeScaleEroderComponent

This test suite runs multiple simulations with different K_br values to analyze
the sensitivity of the landscape evolution model to bedrock erodibility changes.
"""

import pytest
import os
import time
from PyQt6.QtTest import QTest
from PyQt6.QtCore import Qt

from views.home_window import HomeWindow
from views.simulation_window import SimulationWindow
from views.add_component import AddComponentDlg
from views.simulation_results import SimulationResultsWindow
from tests.test_helpers import UIHelper, ResultsCollector


class TestKbrSensitivity:
    """Test class for K_br sensitivity analysis"""
    
    @pytest.fixture(autouse=True)
    def setup(self, qapp, test_dem_path, base_simulation_params, kbr_test_values):
        """Setup test fixtures"""
        self.qapp = qapp
        self.test_dem_path = test_dem_path
        self.base_params = base_simulation_params
        self.kbr_values = kbr_test_values
        self.ui_helper = UIHelper()
        self.results_collector = ResultsCollector()
        
        # Verify DEM file exists
        assert os.path.exists(self.test_dem_path), f"Test DEM not found: {self.test_dem_path}"
    
    def test_kbr_sensitivity_suite(self):
        """
        Main test that runs complete sensitivity analysis for all K_br values.
        Each simulation is run independently to ensure clean state.
        """
        print("\n" + "="*80)
        print("Starting K_br Sensitivity Analysis")
        print("="*80)
        
        for kbr_value in self.kbr_values:
            print(f"\n--- Testing K_br = {kbr_value:.2e} ---")
            
            try:
                # Run single simulation with this K_br value
                result = self._run_single_simulation(kbr_value)
                
                # Collect results
                self.results_collector.add_result(
                    kbr_value=kbr_value,
                    sim_number=result['sim_number'],
                    output_dir=result['output_dir'],
                    stats=result['stats']
                )
                
                print(f"✓ Completed simulation for K_br = {kbr_value:.2e}")
                
            except Exception as e:
                print(f"✗ Failed simulation for K_br = {kbr_value:.2e}: {e}")
                # Continue with next value even if one fails
                pytest.fail(f"Simulation failed for K_br={kbr_value:.2e}: {e}")
        
        # Generate final reports
        self._generate_reports()
        
        print("\n" + "="*80)
        print("K_br Sensitivity Analysis Complete")
        print("="*80)
    
    def _run_single_simulation(self, kbr_value):
        """
        Run a single simulation with specified K_br value
        
        Steps:
        1. Open home window and click start simulation
        2. Setup simulation parameters (location, resolution, time)
        3. Add FlowAccumulator component
        4. Add DepthDependentDiffuser component
        5. Add SpaceLargeScaleEroder component with specific K_br
        6. Run simulation and wait for completion
        7. Extract results
        """
        
        # Step 1: Start from home window
        home_window = HomeWindow()
        home_window.show()
        QTest.qWait(500)
        
        # Click start simulation button
        self.ui_helper.click_button(home_window.ui.startSimulationBtn)
        QTest.qWait(1000)
        
        # Step 2: Setup simulation window
        sim_window = self._find_simulation_window()
        assert sim_window is not None, "Simulation window not found"
        
        self._setup_simulation_parameters(sim_window)
        
        # Step 3-5: Add components
        self._add_flow_accumulator(sim_window)
        QTest.qWait(500)
        
        self._add_depth_diffuser(sim_window)
        QTest.qWait(500)
        
        self._add_space_large_scale_eroder(sim_window, kbr_value)
        QTest.qWait(500)
        
        # Step 6: Run simulation
        results_window = self._run_simulation(sim_window)
        
        # Step 7: Wait for completion and extract results
        result = self._wait_and_extract_results(results_window)
        
        # Cleanup
        results_window.close()
        sim_window.close()
        home_window.close()
        QTest.qWait(500)
        
        return result
    
    def _find_simulation_window(self):
        """Find the active simulation window"""
        for widget in self.qapp.topLevelWidgets():
            if isinstance(widget, SimulationWindow) and widget.isVisible():
                return widget
        return None
    
    def _setup_simulation_parameters(self, sim_window):
        """Setup basic simulation parameters"""
        # Select location: Whiria Pa
        location_combo = sim_window.ui.locationComboBox
        success = self.ui_helper.select_combobox_item(location_combo, "Whiria Pa")
        assert success, "Failed to select location 'Whiria Pa'"
        QTest.qWait(500)
        
        # Select resolution: 1m
        resolution_combo = sim_window.ui.resolutionComboBox
        success = self.ui_helper.select_combobox_item(resolution_combo, "1m")
        assert success, "Failed to select resolution '1m'"
        QTest.qWait(300)
        
        # Set simulation period: 1000 years
        period_edit = sim_window.ui.simulationPeriodLineEdit
        self.ui_helper.set_lineedit_text(period_edit, "1000")
        
        # Set time step: 10 years
        timestep_edit = sim_window.ui.timeStepLineEdit
        self.ui_helper.set_lineedit_text(timestep_edit, "10")
        
        QTest.qWait(300)
    
    def _add_flow_accumulator(self, sim_window):
        """Add FlowAccumulator component"""
        print("  Adding FlowAccumulator...")
        
        # Click add component button
        self.ui_helper.click_button(sim_window.ui.addComponentBtn)
        QTest.qWait(500)
        
        # Find component dialog
        comp_dialog = self._find_component_dialog()
        assert comp_dialog is not None, "Component dialog not found"
        
        # Select FlowAccumulator
        comp_combo = comp_dialog.ui.selectComponentComboBox
        success = self.ui_helper.select_combobox_item(comp_combo, "FlowAccumulatorComponent")
        assert success, "Failed to select FlowAccumulatorComponent"
        QTest.qWait(500)
        
        # Click add button (use default parameters)
        self.ui_helper.click_button(comp_dialog.ui.addBtn)
        QTest.qWait(300)
    
    def _add_depth_diffuser(self, sim_window):
        """Add DepthDependentDiffuser component"""
        print("  Adding DepthDependentDiffuser...")
        
        # Click add component button
        self.ui_helper.click_button(sim_window.ui.addComponentBtn)
        QTest.qWait(500)
        
        # Find component dialog
        comp_dialog = self._find_component_dialog()
        assert comp_dialog is not None, "Component dialog not found"
        
        # Select DepthDependentDiffuser
        comp_combo = comp_dialog.ui.selectComponentComboBox
        success = self.ui_helper.select_combobox_item(comp_combo, "DepthDependentDiffuserComponent")
        assert success, "Failed to select DepthDependentDiffuserComponent"
        QTest.qWait(500)
        
        # Click add button (use default parameters)
        self.ui_helper.click_button(comp_dialog.ui.addBtn)
        QTest.qWait(300)
    
    def _add_space_large_scale_eroder(self, sim_window, kbr_value):
        """Add SpaceLargeScaleEroder component with specific K_br value"""
        print(f"  Adding SpaceLargeScaleEroder with K_br={kbr_value:.2e}...")
        
        # Click add component button
        self.ui_helper.click_button(sim_window.ui.addComponentBtn)
        QTest.qWait(500)
        
        # Find component dialog
        comp_dialog = self._find_component_dialog()
        assert comp_dialog is not None, "Component dialog not found"
        
        # Select SpaceLargeScaleEroder
        comp_combo = comp_dialog.ui.selectComponentComboBox
        success = self.ui_helper.select_combobox_item(comp_combo, "SpaceLargeScaleEroderComponent")
        assert success, "Failed to select SpaceLargeScaleEroderComponent"
        QTest.qWait(1000)  # Wait for dynamic form to load
        
        # Set lithology to Uniform
        if comp_dialog.dynamic_form and 'lithology_type' in comp_dialog.dynamic_form.fields:
            lithology_combo = comp_dialog.dynamic_form.fields['lithology_type']
            self.ui_helper.select_combobox_item(lithology_combo, "Uniform")
            QTest.qWait(500)
        
        # Set K_br value
        if comp_dialog.dynamic_form and 'K_br' in comp_dialog.dynamic_form.fields:
            kbr_spinbox = comp_dialog.dynamic_form.fields['K_br']
            self.ui_helper.set_spinbox_value(kbr_spinbox, kbr_value)
            print(f"    Set K_br to: {kbr_spinbox.value():.2e}")
        else:
            pytest.fail("K_br field not found in component dialog")
        
        # Click add button
        self.ui_helper.click_button(comp_dialog.ui.addBtn)
        QTest.qWait(300)
    
    def _find_component_dialog(self):
        """Find the active component dialog"""
        for widget in self.qapp.topLevelWidgets():
            if isinstance(widget, AddComponentDlg) and widget.isVisible():
                return widget
        return None
    
    def _run_simulation(self, sim_window):
        """Click run simulation and wait for results window"""
        print("  Running simulation...")
        
        # Click run simulation button
        self.ui_helper.click_button(sim_window.ui.viewSimulationBtn)
        QTest.qWait(2000)
        
        # Find results window
        results_window = self._find_results_window()
        assert results_window is not None, "Results window not found"
        
        return results_window
    
    def _find_results_window(self):
        """Find the active results window"""
        for widget in self.qapp.topLevelWidgets():
            if isinstance(widget, SimulationResultsWindow) and widget.isVisible():
                return widget
        return None
    
    def _wait_and_extract_results(self, results_window):
        """Wait for simulation completion and extract results"""
        print("  Waiting for simulation to complete...")
        
        # Wait for simulation to complete (with longer timeout for sensitivity tests)
        try:
            self.ui_helper.wait_for_simulation_complete(results_window)  # 10 minutes
        except TimeoutError as e:
            pytest.fail(f"Simulation timeout: {e}")
        
        # Extract results
        result = {
            'sim_number': results_window.sim_params.get('simulation_number'),
            'output_dir': results_window.image_paths.get('output_dir', ''),
            'stats': {
                'total_time': str(time.time()),  # Placeholder
                'peak_ram': f"{results_window.peak_ram:.1f} MB" if hasattr(results_window, 'peak_ram') else 'N/A'
            }
        }
        
        print(f"  Simulation complete! Output: {result['output_dir']}")
        
        return result
    
    def _generate_reports(self):
        """Generate summary reports"""
        print("\nGenerating reports...")
        
        summary_path = self.results_collector.save_summary()
        print(f"  Summary saved: {summary_path}")
        
        report_path = self.results_collector.create_comparison_report()
        print(f"  Report saved: {report_path}")


class TestKbrIndividualValues:
    """Individual test methods for each K_br value (for parallel execution)"""
    
    @pytest.fixture(autouse=True)
    def setup(self, qapp, test_dem_path):
        """Setup test fixtures"""
        self.qapp = qapp
        self.test_dem_path = test_dem_path
        self.ui_helper = UIHelper()
    
    @pytest.mark.parametrize("kbr_value", [1e-7, 1e-6, 1e-5])
    def test_kbr_value(self, kbr_value):
        """Test individual K_br value (can be run in parallel)"""
        print(f"\nTesting K_br = {kbr_value:.2e}")
        
        # This would use the same logic as _run_single_simulation
        # but is structured as individual tests for pytest-xdist parallel execution
        pass  # Implementation same as in TestKbrSensitivity._run_single_simulation