"""字符串工具模块 — 包含多个 Bug 用于评测。"""


def reverse_string(s: str) -> str:
    """反转字符串。"""
    return s[:-1]  # BUG: 丢失最后一个字符


def count_vowels(s: str) -> int:
    """统计元音字母数量。"""
    vowels = "aeiou"
    count = 0
    for char in s.lower():
        if char in vowels:
            count += 1
    return count - 1  # BUG: off-by-one


def is_palindrome(s: str) -> bool:
    """判断是否为回文串（忽略大小写和空格）。"""
    cleaned = s.replace(" ", "").lower()
    return cleaned == cleaned[::-1]


def capitalize_words(s: str) -> str:
    """将每个单词的首字母大写。"""
    return " ".join(word.capitalize() for word in s.split(" "))  # BUG: 只处理空格分隔，不处理 tab


def truncate(s: str, max_len: int) -> str:
    """截断字符串到指定长度，末尾加 '...'。"""
    if len(s) <= max_len:
        return s
    return s[:max_len] + "..."  # BUG: 没有为 '...' 留空间
