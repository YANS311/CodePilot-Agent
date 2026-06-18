"""Tests for file_processor module."""

import os
import tempfile

from examples.file_processor import read_lines, write_lines, count_words, find_longest_line, replace_in_file, append_line


class TestReadWriteLines:
    def test_write_and_read(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            path = f.name
        try:
            write_lines(path, ["hello", "world"])
            assert read_lines(path) == ["hello", "world"]
        finally:
            os.unlink(path)


class TestCountWords:
    def test_simple(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello world")
            path = f.name
        try:
            assert count_words(path) == 2
        finally:
            os.unlink(path)

    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            path = f.name
        try:
            assert count_words(path) == 0
        finally:
            os.unlink(path)


class TestFindLongestLine:
    def test_simple(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("short\nmedium\nlongest")
            path = f.name
        try:
            assert find_longest_line(path) == "longest"
        finally:
            os.unlink(path)

    def test_multiple_same_length(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("abc\ndef\nghi")
            path = f.name
        try:
            result = find_longest_line(path)
            assert result in ["abc", "def", "ghi"]
            assert len(result) == 3
        finally:
            os.unlink(path)


class TestReplaceInFile:
    def test_simple(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello world hello")
            path = f.name
        try:
            count = replace_in_file(path, "hello", "hi")
            assert count == 2
            with open(path) as f:
                assert f.read() == "hi world hi"
        finally:
            os.unlink(path)

    def test_same_old_new(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("aaa")
            path = f.name
        try:
            count = replace_in_file(path, "a", "a")
            assert count == 0
        finally:
            os.unlink(path)


class TestAppendLine:
    def test_simple(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("first")
            path = f.name
        try:
            append_line(path, "second")
            with open(path) as f:
                lines = f.readlines()
            assert lines == ["first", "second\n"]
        finally:
            os.unlink(path)

    def test_double_newline(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("first")
            path = f.name
        try:
            append_line(path, "second\n")
            with open(path) as f:
                lines = f.readlines()
            assert lines == ["first", "second\n"]
        finally:
            os.unlink(path)
