"""Tests for string_utils module."""

from examples.string_utils import reverse_string, count_vowels, is_palindrome, capitalize_words, truncate


class TestReverseString:
    def test_simple(self):
        assert reverse_string("hello") == "olleh"

    def test_single_char(self):
        assert reverse_string("a") == "a"

    def test_empty(self):
        assert reverse_string("") == ""


class TestCountVowels:
    def test_hello(self):
        assert count_vowels("hello") == 2

    def test_empty(self):
        assert count_vowels("") == 0

    def test_all_vowels(self):
        assert count_vowels("aeiou") == 5


class TestIsPalindrome:
    def test_palindrome(self):
        assert is_palindrome("racecar") is True

    def test_not_palindrome(self):
        assert is_palindrome("hello") is False

    def test_with_spaces(self):
        assert is_palindrome("A man a plan a canal Panama") is True


class TestCapitalizeWords:
    def test_simple(self):
        assert capitalize_words("hello world") == "Hello World"

    def test_single_word(self):
        assert capitalize_words("hello") == "Hello"

    def test_with_tabs(self):
        assert capitalize_words("hello\tworld") == "Hello\tWorld"


class TestTruncate:
    def test_short_string(self):
        assert truncate("hello", 10) == "hello"

    def test_exact_length(self):
        assert truncate("hello", 5) == "hello"

    def test_long_string(self):
        assert truncate("hello world", 5) == "hello..."
