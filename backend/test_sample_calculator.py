"""
test_sample_calculator.py — Test script that fails due to the bug in sample_calculator.py.
"""
from sample_calculator import calculate_total


def test_calculate_total():
    items = [
        {"price": 100, "tax": 10},
        {"price": 50, "tax": 5},
    ]
    # Expected: (100 + 10) + (50 + 5) = 165
    result = calculate_total(items)
    print(f"Calculated total: {result}")
    assert result == 165, f"Expected 165, got {result}"
    print("Test Passed!")


if __name__ == "__main__":
    test_calculate_total()
