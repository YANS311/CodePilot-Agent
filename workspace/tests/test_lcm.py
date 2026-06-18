"""
LCM 最小公倍数单元测试
"""

import pytest
from examples.lcm import lcm, lcm_multiple, lcm_range


class TestLCM:
    """测试两个数的 lcm 函数"""

    def test_basic(self):
        assert lcm(4, 6) == 12
        assert lcm(7, 5) == 35
        assert lcm(12, 18) == 36

    def test_commutative(self):
        """LCM 满足交换律"""
        assert lcm(6, 8) == lcm(8, 6)

    def test_same_number(self):
        assert lcm(7, 7) == 7
        assert lcm(1, 1) == 1

    def test_one(self):
        """含 1 的情况下 LCM 为另一个数"""
        assert lcm(1, 9) == 9
        assert lcm(5, 1) == 5

    def test_large_numbers(self):
        assert lcm(1234, 4321) == 5332114

    def test_zero_raises_error(self):
        with pytest.raises(ValueError, match="0 没有最小公倍数"):
            lcm(0, 5)
        with pytest.raises(ValueError, match="0 没有最小公倍数"):
            lcm(5, 0)

    def test_negative_numbers(self):
        """负数与正数的 LCM 相同（取绝对值）"""
        assert lcm(-4, 6) == 12
        assert lcm(4, -6) == 12
        assert lcm(-4, -6) == 12


class TestLCMMultiple:
    """测试多个数的 lcm_multiple 函数"""

    def test_basic(self):
        assert lcm_multiple(3, 5, 7) == 105
        assert lcm_multiple(2, 3, 4, 6) == 12

    def test_two_numbers(self):
        """两个数与直接调用 lcm 结果一致"""
        assert lcm_multiple(4, 6) == lcm(4, 6)

    def test_single_number_raises(self):
        with pytest.raises(ValueError, match="至少需要两个整数"):
            lcm_multiple(5)

    def test_with_one(self):
        assert lcm_multiple(1, 2, 3, 4, 5) == 60

    def test_large_set(self):
        assert lcm_multiple(6, 7, 8, 9, 10) == 2520


class TestLCMRange:
    """测试范围的 lcm_range 函数"""

    def test_basic(self):
        assert lcm_range(1, 5) == 60
        assert lcm_range(1, 10) == 2520

    def test_single_range(self):
        """start == end"""
        assert lcm_range(3, 3) == 3

    def test_start_less_than_one_raises(self):
        with pytest.raises(ValueError, match="起始值必须 >= 1"):
            lcm_range(0, 5)

    def test_end_less_than_start_raises(self):
        with pytest.raises(ValueError, match="结束值必须 >= 起始值"):
            lcm_range(5, 3)
