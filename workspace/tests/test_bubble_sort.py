"""
冒泡排序单元测试
"""

import pytest
from examples.bubble_sort import (
    bubble_sort,
    bubble_sort_inplace,
    bubble_sort_optimized,
    cocktail_sort,
)


class TestBubbleSort:
    """测试经典冒泡排序"""

    def test_simple(self):
        assert bubble_sort([64, 34, 25, 12, 22, 11, 90]) == [11, 12, 22, 25, 34, 64, 90]

    def test_already_sorted(self):
        assert bubble_sort([1, 2, 3, 4, 5]) == [1, 2, 3, 4, 5]

    def test_reverse_sorted(self):
        assert bubble_sort([5, 4, 3, 2, 1]) == [1, 2, 3, 4, 5]

    def test_with_duplicates(self):
        assert bubble_sort([3, 1, 4, 1, 5, 9, 2, 6, 5]) == [1, 1, 2, 3, 4, 5, 5, 6, 9]

    def test_single_element(self):
        assert bubble_sort([42]) == [42]

    def test_empty_list(self):
        assert bubble_sort([]) == []

    def test_negative_numbers(self):
        assert bubble_sort([-3, 0, -1, 5, -7]) == [-7, -3, -1, 0, 5]

    def test_float_numbers(self):
        assert bubble_sort([3.14, 1.41, 2.72, 1.61]) == [1.41, 1.61, 2.72, 3.14]

    def test_strings(self):
        assert bubble_sort(["banana", "apple", "cherry", "date"]) == [
            "apple", "banana", "cherry", "date"
        ]

    def test_original_unchanged(self):
        """bubble_sort 不应修改原列表"""
        original = [3, 1, 2]
        bubble_sort(original)
        assert original == [3, 1, 2]


class TestBubbleSortInplace:
    """测试原地冒泡排序"""

    def test_simple(self):
        arr = [64, 34, 25, 12, 22, 11, 90]
        bubble_sort_inplace(arr)
        assert arr == [11, 12, 22, 25, 34, 64, 90]

    def test_single_element(self):
        arr = [42]
        bubble_sort_inplace(arr)
        assert arr == [42]

    def test_empty_list(self):
        arr = []
        bubble_sort_inplace(arr)
        assert arr == []

    def test_duplicates(self):
        arr = [2, 1, 2]
        bubble_sort_inplace(arr)
        assert arr == [1, 2, 2]


class TestBubbleSortOptimized:
    """测试优化冒泡排序（提前退出机制）"""

    def test_simple(self):
        assert bubble_sort_optimized([64, 34, 25, 12, 22, 11, 90]) == [
            11, 12, 22, 25, 34, 64, 90
        ]

    def test_already_sorted(self):
        """已有序列表应提前退出"""
        assert bubble_sort_optimized([1, 2, 3, 4, 5]) == [1, 2, 3, 4, 5]

    def test_reverse_sorted(self):
        assert bubble_sort_optimized([5, 4, 3, 2, 1]) == [1, 2, 3, 4, 5]

    def test_duplicates(self):
        assert bubble_sort_optimized([3, 1, 4, 1, 5]) == [1, 1, 3, 4, 5]

    def test_empty(self):
        assert bubble_sort_optimized([]) == []


class TestCocktailSort:
    """测试鸡尾酒排序（双向冒泡排序）"""

    def test_simple(self):
        assert cocktail_sort([64, 34, 25, 12, 22, 11, 90]) == [
            11, 12, 22, 25, 34, 64, 90
        ]

    def test_already_sorted(self):
        assert cocktail_sort([1, 2, 3, 4, 5]) == [1, 2, 3, 4, 5]

    def test_reverse_sorted(self):
        assert cocktail_sort([5, 4, 3, 2, 1]) == [1, 2, 3, 4, 5]

    def test_with_duplicates(self):
        assert cocktail_sort([3, 1, 4, 1, 5, 9, 2]) == [1, 1, 2, 3, 4, 5, 9]

    def test_single_element(self):
        assert cocktail_sort([42]) == [42]

    def test_empty_list(self):
        assert cocktail_sort([]) == []

    def test_negative_numbers(self):
        assert cocktail_sort([-3, 0, -1, 5, -7]) == [-7, -3, -1, 0, 5]

    def test_strings(self):
        assert cocktail_sort(["banana", "apple", "cherry", "date"]) == [
            "apple", "banana", "cherry", "date"
        ]

    def test_original_unchanged(self):
        """cocktail_sort 不应修改原列表"""
        original = [3, 1, 2]
        cocktail_sort(original)
        assert original == [3, 1, 2]
