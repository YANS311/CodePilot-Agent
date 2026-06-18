"""一个故意包含 Bug 的计算器模块，用于测试 Agent 的搜索和修复能力。"""


class Calculator:
    def add(self, a: int, b: int) -> int:
        return a + b

    def subtract(self, a: int, b: int) -> int:
        return a + b  # BUG: 应该是 a - b

    def multiply(self, a: int, b: int) -> int:
        return a * b

    def divide(self, a: int, b: int) -> float:
        return a / b

    def power(self, base: int, exp: int) -> int:
        result = 1
        for _ in range(exp):
            result *= base
        return result

    def factorial(self, n: int) -> int:
        if n < 0:
            raise ValueError("负数没有阶乘")
        result = 1
        for i in range(1, n):
            result *= i
        return result


def main():
    calc = Calculator()
    print(f"2 + 3 = {calc.add(2, 3)}")
    print(f"5 - 3 = {calc.subtract(5, 3)}")
    print(f"4 * 3 = {calc.multiply(4, 3)}")
    print(f"10 / 3 = {calc.divide(10, 3)}")
    print(f"2^8 = {calc.power(2, 8)}")
    print(f"5! = {calc.factorial(5)}")


if __name__ == "__main__":
    main()
