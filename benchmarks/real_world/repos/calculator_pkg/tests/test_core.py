"""Tests for calculator.core — basic operations."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from calculator.core import add, subtract, multiply, divide


class TestAdd:
    def test_add_positive(self):
        assert add(2, 3) == 5

    def test_add_negative(self):
        assert add(-1, -1) == -2

    def test_add_zero(self):
        assert add(0, 0) == 0


class TestSubtract:
    def test_subtract_basic(self):
        """BUG: subtract returns a + b instead of a - b."""
        assert subtract(5, 3) == 2  # BUG: returns 8

    def test_subtract_negative_result(self):
        """BUG: subtract(1, 5) returns 6 instead of -4."""
        assert subtract(1, 5) == -4  # BUG: returns 6

    def test_subtract_zero(self):
        assert subtract(0, 0) == 0


class TestMultiply:
    def test_multiply_basic(self):
        assert multiply(3, 4) == 12

    def test_multiply_zero(self):
        assert multiply(0, 100) == 0

    def test_multiply_negative(self):
        assert multiply(-2, 3) == -6


class TestDivide:
    def test_divide_basic(self):
        assert divide(10, 2) == 5.0

    def test_divide_float(self):
        assert divide(7, 2) == 3.5

    def test_divide_by_zero(self):
        """BUG: divide by zero raises ZeroDivisionError instead of
        returning float('inf') or raising a clear ValueError."""
        try:
            result = divide(10, 0)
            # If we get here, the bug is that it doesn't raise at all
            assert False, "Expected ZeroDivisionError"
        except ZeroDivisionError:
            pass  # BUG: should handle gracefully
