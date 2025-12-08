#!/usr/bin/env python3
"""
Convenience script to run K_br sensitivity analysis tests

Usage:
    python run_kbr_tests.py           # Run all K_br tests sequentially
    python run_kbr_tests.py --fast    # Run with fewer K_br values
    python run_kbr_tests.py --report  # Generate HTML report
"""

import sys
import subprocess
import argparse
from pathlib import Path

def run_tests(args):
    """Run the K_br sensitivity tests"""
    
    # Base pytest command
    pytest_args = [
        sys.executable, "-m", "pytest",
        "tests/test_kbr_sensitivity.py",
        "-v",
        "--tb=short"
    ]
    
    # Add HTML report if requested
    if args.report:
        pytest_args.extend([
            "--html=tests/sensitivity_results/test_report.html",
            "--self-contained-html"
        ])
    
    # Add coverage if requested
    if args.coverage:
        pytest_args.extend([
            "--cov=engine",
            "--cov-report=html:tests/sensitivity_results/coverage"
        ])
    
    # Select test method based on mode
    if args.fast:
        # Run with fewer K_br values for quick testing
        print("Running FAST mode with limited K_br values...")
        pytest_args.append("-k")
        pytest_args.append("test_kbr_sensitivity_suite")
    else:
        # Run all tests
        print("Running FULL sensitivity analysis...")
        pytest_args.append("tests/test_kbr_sensitivity.py::TestKbrSensitivity::test_kbr_sensitivity_suite")
    
    # Run pytest
    print(f"Running: {' '.join(pytest_args)}\n")
    result = subprocess.run(pytest_args)
    
    return result.returncode

def main():
    parser = argparse.ArgumentParser(
        description="Run K_br sensitivity analysis tests",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Run quick test with fewer K_br values"
    )
    
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate HTML test report"
    )
    
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="Generate code coverage report"
    )
    
    args = parser.parse_args()
    
    # Ensure test results directory exists
    Path("tests/sensitivity_results").mkdir(parents=True, exist_ok=True)
    
    # Run tests
    exit_code = run_tests(args)
    
    # Print summary
    print("\n" + "="*80)
    if exit_code == 0:
        print("✓ All tests passed!")
        if args.report:
            print("  HTML report: tests/sensitivity_results/test_report.html")
        if args.coverage:
            print("  Coverage report: tests/sensitivity_results/coverage/index.html")
    else:
        print("✗ Some tests failed")
    print("="*80)
    
    return exit_code

if __name__ == "__main__":
    sys.exit(main())