"""Calculator 测试 — 用于验证 Agent 修复结果。"""

import pytest
from examples.buggy_calculator import Calculator


class TestCalculator:
    def setup_method(self):
        self.calc = Calculator()

    def test_add(self):
        assert self.calc.add(2, 3) == 5

    def test_subtract(self):
        assert self.calc.subtract(5, 3) == 2

    def test_multiply(self):
        assert self.calc.multiply(4, 3) == 12

    def test_divide(self):
        assert self.calc.divide(10, 3) == pytest.approx(3.333, abs=0.01)

    def test_divide_zero(self):
        with pytest.raises(ValueError):
            self.calc.divide(10, 0)

    def test_power(self):
        assert self.calc.power(2, 8) == 256

    def test_factorial(self):
        assert self.calc.factorial(5) == 120
        assert self.calc.factorial(0) == 1
        assert self.calc.factorial(1) == 1

    def test_factorial_negative(self):
        with pytest.raises(ValueError):
            self.calc.factorial(-1)


class TestTypeValidation:
    def setup_method(self):
        self.calc = Calculator()

    def test_add_type_error(self):
        with pytest.raises(TypeError):
            self.calc.add("a", 1)

    def test_subtract_type_error(self):
        with pytest.raises(TypeError):
            self.calc.subtract(1, "b")
