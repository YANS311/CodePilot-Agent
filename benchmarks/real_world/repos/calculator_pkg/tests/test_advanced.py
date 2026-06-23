"""Tests for calculator.advanced — advanced operations."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from calculator.advanced import factorial, lcm, gcd, fibonacci


class TestFactorial:
    def test_factorial_0(self):
        assert factorial(0) == 1

    def test_factorial_1(self):
        assert factorial(1) == 1

    def test_factorial_5(self):
        """BUG: factorial(5) returns 24 instead of 120 (off-by-one)."""
        assert factorial(5) == 120  # BUG: returns 24

    def test_factorial_negative(self):
        import pytest
        with pytest.raises(ValueError):
            factorial(-1)


class TestLcm:
    def test_lcm_two(self):
        assert lcm(4, 6) == 12

    def test_lcm_coprime(self):
        assert lcm(7, 13) == 91

    def test_lcm_negative(self):
        """BUG: lcm(-4, 6) should return 12, not -12."""
        assert lcm(-4, 6) == 12  # BUG: returns -12

    def test_lcm_single(self):
        assert lcm(5) == 5


class TestGcd:
    def test_gcd_two(self):
        assert gcd(12, 8) == 4

    def test_gcd_coprime(self):
        assert gcd(7, 13) == 1

    def test_gcd_three(self):
        assert gcd(12, 8, 6) == 2


class TestFibonacci:
    def test_fib_zero(self):
        assert fibonacci(0) == []

    def test_fib_one(self):
        assert fibonacci(1) == [0]

    def test_fib_ten(self):
        assert fibonacci(10) == [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]
