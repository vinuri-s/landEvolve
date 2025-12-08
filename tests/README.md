# K_br Sensitivity Analysis Tests

This directory contains automated sensitivity analysis tests for the K_br parameter in the SpaceLargeScaleEroderComponent.

## Installation

1. Install test dependencies:
```bash
pip install -r requirements-test.txt
```

2. Ensure your database is set up with required data:
   - Location: "Whiria Pa"
   - Resolution: "1m"
   - DEM file: `resources/inputs/whiriapa/whiriapa_1m.tif`

## Running Tests

### Method 1: Using the convenience script (Recommended)

```bash
# Run full sensitivity analysis (all K_br values)
python run_kbr_tests.py

# Run fast test (limited K_br values)
python run_kbr_tests.py --fast

# Generate HTML report
python run_kbr_tests.py --report

# Generate coverage report
python run_kbr_tests.py --coverage
```

### Method 2: Using pytest directly

```bash
# Run all K_br sensitivity tests
pytest tests/test_kbr_sensitivity.py -v

# Run specific test class
pytest tests/test_kbr_sensitivity.py::TestKbrSensitivity -v

# Run with HTML report
pytest tests/test_kbr_sensitivity.py --html=tests/sensitivity_results/test_report.html --self-contained-html
```

## Test Structure

```
tests/
├── __init__.py                    # Package marker
├── conftest.py                    # Pytest fixtures and configuration
├── test_helpers.py                # Helper functions for UI interaction
├── test_kbr_sensitivity.py        # Main sensitivity analysis tests
├── sensitivity_results/           # Test outputs (created automatically)
│   ├── sensitivity_summary.json   # JSON summary of all runs
│   ├── sensitivity_report.md      # Markdown comparison report
│   └── test_report.html          # HTML test report (if --report used)
└── README.md                      # This file
```

## Test Workflow

Each K_br value test follows this workflow:

1. **Launch Application**: Start from HomeWindow
2. **Navigate to Simulation Setup**: Click "Start Simulation"
3. **Configure Parameters**:
   - Location: Whiria Pa
   - Resolution: 1m
   - Simulation Period: 1000 years
   - Time Step: 10 years
4. **Add Components** (in order):
   - FlowAccumulatorComponent (default parameters)
   - DepthDependentDiffuserComponent (default parameters)
   - SpaceLargeScaleEroderComponent:
     - lithology_type: Uniform
     - K_br: *test value*
5. **Run Simulation**: Wait for completion (up to 10 minutes)
6. **Extract Results**: Collect output paths and statistics
7. **Cleanup**: Close windows and prepare for next test

## K_br Test Values

The default test suite uses these K_br values:

- 1e-10 (Very low erodibility)
- 1e-9
- 1e-8
- 1e-7 (Default)
- 1e-6
- 1e-5
- 1e-4 (High erodibility)

## Results Analysis

After running the tests, you'll find:

1. **Individual Simulation Outputs**: 
   - Location: `resources/outputs/simulation_N/`
   - Contains: DEM outputs, plots, GeoTIFFs

2. **Summary JSON**: 
   - Location: `tests/sensitivity_results/sensitivity_summary.json`
   - Contains: All test results with parameters and statistics

3. **Comparison Report**: 
   - Location: `tests/sensitivity_results/sensitivity_report.md`
   - Contains: Human-readable comparison of all runs

4. **Test Report** (if --report used): 
   - Location: `tests/sensitivity_results/test_report.html`
   - Contains: Detailed pytest execution report

## Customization

### Modify K_br Values

Edit `tests/conftest.py`:

```python
@pytest.fixture
def kbr_test_values():
    """K_br values for sensitivity testing"""
    return [
        1e-8,   # Your custom values
        5e-8,
        1e-7,
        # ... add more values
    ]
```

### Change Simulation Parameters

Edit `tests/conftest.py`:

```python
@pytest.fixture
def base_simulation_params():
    """Base simulation parameters"""
    return {
        'simulation_period': 500,  # Change duration
        'time_step': 5,            # Change time step
        # ... other parameters
    }
```

### Add Additional Tests

Create new test methods in `test_kbr_sensitivity.py`:

```python
def test_custom_scenario(self, qapp):
    """Your custom test"""
    # Your test code here
    pass
```

## Troubleshooting

### Tests timeout
- Increase timeout in `pytest.ini`: `timeout = 1800` (30 minutes)
- Or use `@pytest.mark.timeout(1800)` decorator on specific tests

### UI interaction fails
- Check that XDisplay is available (Linux)
- On headless systems, use Xvfb: `xvfb-run pytest tests/`

### Database not found
- Ensure `db/app_data.db` exists
- Run your main application once to initialize the database

### Component not found
- Verify component names in database match exactly
- Check that all required components are in the database

## Notes

- Each simulation takes 5-10 minutes depending on your hardware
- Full suite (7 K_br values) takes approximately 35-70 minutes
- Tests create temporary windows - don't interact with them during execution
- Results are stored permanently for later analysis

## CI/CD Integration

To run tests in CI pipeline:

```yaml
# .github/workflows/sensitivity_tests.yml
name: K_br Sensitivity Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-test.txt
      - name: Run tests
        run: xvfb-run python run_kbr_tests.py --report
      - name: Upload results
        uses: actions/upload-artifact@v2
        with:
          name: test-results
          path: tests/sensitivity_results/
```