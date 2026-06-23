"""Basic math operations.

BUG 1: subtract() implemented as addition (returns a + b instead of a - b)
BUG 2: divide() has no zero-division guard (raises ZeroDivisionError)
"""


def add(a: float, b: float) -> float:
    """Return the sum of a and b."""
    return a + b


def subtract(a: float, b: float) -> float:
    """Return the difference of a and b.

    BUG: Returns a + b instead of a - b.
    """
    return a + b  # BUG: should be a - b


def multiply(a: float, b: float) -> float:
    """Return the product of a and b."""
    return a * b


def divide(a: float, b: float) -> float:
    """Return the quotient of a and b.

    BUG: No zero-division check — raises ZeroDivisionError instead of
    returning a user-friendly value or raising a clear error.
    """
    return a / b  # BUG: no guard for b == 0
