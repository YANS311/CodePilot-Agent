"""Fibonacci sequence example.

This module is used by agent demos that ask the model to add defensive
handling for invalid inputs.
"""


def fibonacci(n: int) -> int | None:
    """Return the nth Fibonacci number.

    The sequence is defined as:
        F(0) = 0
        F(1) = 1
        F(n) = F(n - 1) + F(n - 2), for n >= 2

    Non-integer inputs return None. Negative integers raise ValueError.
    """
    if type(n) is not int:
        return None

    if n < 0:
        raise ValueError("n must be a non-negative integer")
    if n <= 1:
        return n

    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b


if __name__ == "__main__":
    for i in range(11):
        print(f"fibonacci({i}) = {fibonacci(i)}")

    print(f"fibonacci(20) = {fibonacci(20)}")  # 6765
    print(f"fibonacci(30) = {fibonacci(30)}")  # 832040
    print(f"fibonacci(50) = {fibonacci(50)}")  # 12586269025
