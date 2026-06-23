"""Advanced math operations.

BUG 1: factorial() has an off-by-one — stops one iteration too early.
BUG 2: lcm() does not handle negative inputs correctly (ignores sign).
"""

import math
from typing import List


def factorial(n: int) -> int:
    """Compute the factorial of n (n!).

    BUG: Off-by-one — the loop stops at n-1 instead of n,
    so factorial(5) returns 24 instead of 120.
    """
    if n < 0:
        raise ValueError("Factorial is not defined for negative numbers")
    result = 1
    for i in range(1, n):  # BUG: should be range(1, n + 1)
        result *= i
    return result


def lcm(*args: int) -> int:
    """Compute the least common multiple of the given integers.

    BUG: Does not take absolute values, so lcm(-4, 6) returns -12
    instead of 12.
    """
    if not args:
        raise ValueError("lcm requires at least one argument")
    result = args[0]
    for val in args[1:]:  # BUG: should use abs() around both operands
        result = result * val // math.gcd(abs(result), val)
    return result


def gcd(*args: int) -> int:
    """Compute the greatest common divisor of the given integers."""
    if not args:
        raise ValueError("gcd requires at least one argument")
    result = args[0]
    for val in args[1:]:
        result = math.gcd(result, val)
    return result


def fibonacci(n: int) -> List[int]:
    """Return the first n Fibonacci numbers."""
    if n <= 0:
        return []
    seq = [0, 1]
    while len(seq) < n:
        seq.append(seq[-1] + seq[-2])
    return seq[:n]
