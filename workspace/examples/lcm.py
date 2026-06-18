"""
最小公倍数 (Least Common Multiple, LCM)

提供多种方式计算两个或多个整数的最小公倍数。
"""

import math
from functools import reduce
from typing import List


def lcm(a: int, b: int) -> int:
    """
    计算两个整数 a 和 b 的最小公倍数。

    公式: lcm(a, b) = |a * b| / gcd(a, b)

    参数:
        a: 第一个整数
        b: 第二个整数

    返回:
        a 和 b 的最小公倍数

    异常:
        ValueError: 如果 a 或 b 为 0
    """
    if a == 0 or b == 0:
        raise ValueError("0 没有最小公倍数")
    return abs(a * b) // math.gcd(a, b)


def lcm_multiple(*numbers: int) -> int:
    """
    计算多个整数的最小公倍数。

    参数:
        *numbers: 两个或以上的整数

    返回:
        所有整数的最小公倍数

    异常:
        ValueError: 如果参数少于 2 个，或包含 0
    """
    if len(numbers) < 2:
        raise ValueError("至少需要两个整数")
    return reduce(lcm, numbers)


def lcm_range(start: int, end: int) -> int:
    """
    计算从 start 到 end（包含）范围内所有整数的最小公倍数。

    参数:
        start: 起始整数（必须 >= 1）
        end:   结束整数（必须 >= start）

    返回:
        范围内所有整数的最小公倍数

    异常:
        ValueError: 如果参数不合法
    """
    if start < 1:
        raise ValueError("起始值必须 >= 1")
    if end < start:
        raise ValueError("结束值必须 >= 起始值")
    return lcm_multiple(*range(start, end + 1))


# ===== 示例 =====

if __name__ == "__main__":
    # 两个数
    print(f"lcm(4, 6)   = {lcm(4, 6)}")       # 12
    print(f"lcm(7, 5)   = {lcm(7, 5)}")       # 35
    print(f"lcm(12, 18) = {lcm(12, 18)}")     # 36

    # 多个数
    print(f"lcm(3, 5, 7)       = {lcm_multiple(3, 5, 7)}")          # 105
    print(f"lcm(2, 3, 4, 6)    = {lcm_multiple(2, 3, 4, 6)}")      # 12

    # 范围
    print(f"lcm_range(1, 5)    = {lcm_range(1, 5)}")               # 60
    print(f"lcm_range(1, 10)   = {lcm_range(1, 10)}")              # 2520
