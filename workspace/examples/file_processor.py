"""文件处理模块 — 包含多个 Bug 用于评测。"""

from __future__ import annotations

from pathlib import Path


def read_lines(path: str) -> list[str]:
    """读取文件所有行（去除换行符）。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"文件不存在: {path}")
    return p.read_text(encoding="utf-8").splitlines()


def write_lines(path: str, lines: list[str]) -> int:
    """写入多行到文件，返回写入的字节数。"""
    content = "\n".join(lines)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return len(content.encode("utf-8"))


def count_words(path: str) -> int:
    """统计文件中的单词数。"""
    lines = read_lines(path)
    count = 0
    for line in lines:
        count += len(line.split())  # BUG: 空行会算作 0 个单词，但 split() 对空字符串返回 []
    return count


def find_longest_line(path: str) -> str:
    """找到文件中最长的行。"""
    lines = read_lines(path)
    if not lines:
        return ""
    longest = lines[0]
    for line in lines[1:]:
        if len(line) > len(longest):
            longest = line
    return longest  # BUG: 如果有多行同为最长，只返回最后一个


def replace_in_file(path: str, old: str, new: str) -> int:
    """替换文件中的字符串，返回替换次数。"""
    p = Path(path)
    content = p.read_text(encoding="utf-8")
    new_content = content.replace(old, new)
    count = content.count(old)
    p.write_text(new_content, encoding="utf-8")
    return count  # BUG: 如果 old 和 new 相同，count 应该是 0，但这里返回了实际出现次数


def append_line(path: str, line: str) -> None:
    """追加一行到文件末尾。"""
    p = Path(path)
    with open(p, "a", encoding="utf-8") as f:
        f.write(line + "\n")  # BUG: 如果 line 已经以 \n 结尾，会多一个空行
