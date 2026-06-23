"""
冒泡排序 (Bubble Sort)

提供多种方式对列表进行冒泡排序，包括经典冒泡、优化冒泡和双向冒泡（鸡尾酒排序）。
"""

from typing import List, TypeVar

T = TypeVar("T")


def bubble_sort(arr: List[T]) -> List[T]:
    """
    经典冒泡排序。

    重复遍历列表，依次比较相邻元素，如果顺序错误则交换。
    每轮遍历将当前未排序部分的最大元素"冒泡"到最后。

    参数:
        arr: 待排序的列表

    返回:
        排序后的新列表（不修改原列表）

    时间复杂度: O(n²)
    空间复杂度: O(n) — 返回新列表
    """
    if not arr:
        return []

    result = arr[:]  # 复制一份，不修改原列表
    n = len(result)

    for i in range(n - 1):
        for j in range(n - 1 - i):
            if result[j] > result[j + 1]:
                result[j], result[j + 1] = result[j + 1], result[j]

    return result


def bubble_sort_inplace(arr: List[T]) -> None:
    """
    原地冒泡排序（修改原列表）。

    参数:
        arr: 待排序的列表（会被原地修改）
    """
    n = len(arr)

    for i in range(n - 1):
        for j in range(n - 1 - i):
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]


def bubble_sort_optimized(arr: List[T]) -> List[T]:
    """
    优化冒泡排序 — 增加提前退出机制。

    如果某一轮遍历中没有发生任何交换，说明列表已有序，提前终止。

    参数:
        arr: 待排序的列表

    返回:
        排序后的新列表（不修改原列表）
    """
    if not arr:
        return []

    result = arr[:]
    n = len(result)

    for i in range(n - 1):
        swapped = False
        for j in range(n - 1 - i):
            if result[j] > result[j + 1]:
                result[j], result[j + 1] = result[j + 1], result[j]
                swapped = True
        if not swapped:
            break

    return result


def cocktail_sort(arr: List[T]) -> List[T]:
    """
    鸡尾酒排序（双向冒泡排序）。

    每轮遍历交替进行从左到右和从右到左的冒泡，
    可以更快地将小元素移到前端。

    参数:
        arr: 待排序的列表

    返回:
        排序后的新列表（不修改原列表）
    """
    if not arr:
        return []

    result = arr[:]
    n = len(result)
    left, right = 0, n - 1

    while left < right:
        # 从左到右：将最大元素冒泡到右侧
        new_right = left
        for i in range(left, right):
            if result[i] > result[i + 1]:
                result[i], result[i + 1] = result[i + 1], result[i]
                new_right = i
        right = new_right

        if left >= right:
            break

        # 从右到左：将最小元素冒泡到左侧
        new_left = right
        for i in range(right, left, -1):
            if result[i - 1] > result[i]:
                result[i - 1], result[i] = result[i], result[i - 1]
                new_left = i
        left = new_left

    return result


# ===== 示例 =====

if __name__ == "__main__":
    # 经典冒泡排序
    data = [64, 34, 25, 12, 22, 11, 90]
    print(f"原始列表:          {data}")
    print(f"bubble_sort:       {bubble_sort(data)}")
    print(f"原列表未改变:      {data}")

    # 原地排序
    data_copy = data[:]
    bubble_sort_inplace(data_copy)
    print(f"bubble_sort_inplace: {data_copy}")

    # 优化冒泡排序
    print(f"bubble_sort_optimized: {bubble_sort_optimized(data)}")

    # 鸡尾酒排序
    print(f"cocktail_sort:     {cocktail_sort(data)}")

    # 字符串排序
    words = ["banana", "apple", "cherry", "date"]
    print(f"\n字符串排序:")
    print(f"原始: {words}")
    print(f"排序: {bubble_sort(words)}")

    # 空列表
    print(f"\n空列表: {bubble_sort([])}")

    # 已有序列表（测试优化冒泡的提前退出）
    sorted_data = [1, 2, 3, 4, 5, 6]
    print(f"已有序列表: {bubble_sort_optimized(sorted_data)}")
