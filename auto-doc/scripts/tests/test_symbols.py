"""Tests for lib/symbols.py -- AST-based symbol extraction.

Tests extract_function_signatures() alongside existing extract_python_symbols().
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from lib.symbols import extract_function_signatures


class TestExtractFunctionSignatures:
    """extract_function_signatures() extracts parameter names from functions."""

    def test_simple_function(self):
        """Single function with positional params."""
        source = "def greet(name, greeting):\n    pass\n"
        sigs = extract_function_signatures(source)
        assert sigs == {"greet": ["name", "greeting"]}

    def test_class_method_excludes_self(self):
        """Class method excludes 'self' from parameter list."""
        source = (
            "class Foo:\n"
            "    def bar(self, x, y):\n"
            "        pass\n"
        )
        sigs = extract_function_signatures(source)
        assert sigs == {"bar": ["x", "y"]}

    def test_classmethod_excludes_cls(self):
        """@classmethod excludes 'cls' from parameter list."""
        source = (
            "class Foo:\n"
            "    @classmethod\n"
            "    def create(cls, data):\n"
            "        pass\n"
        )
        sigs = extract_function_signatures(source)
        assert sigs == {"create": ["data"]}

    def test_async_function(self):
        """Async function parameters extracted."""
        source = "async def fetch(url, timeout):\n    pass\n"
        sigs = extract_function_signatures(source)
        assert sigs == {"fetch": ["url", "timeout"]}

    def test_keyword_only_args(self):
        """Keyword-only args (after *) are included."""
        source = "def connect(host, *, port, ssl):\n    pass\n"
        sigs = extract_function_signatures(source)
        assert sigs == {"connect": ["host", "port", "ssl"]}

    def test_no_params(self):
        """Function with no parameters returns empty list."""
        source = "def noop():\n    pass\n"
        sigs = extract_function_signatures(source)
        assert sigs == {"noop": []}

    def test_multiple_functions(self):
        """Multiple functions each extracted separately."""
        source = (
            "def add(a, b):\n    pass\n\n"
            "def mul(x, y):\n    pass\n"
        )
        sigs = extract_function_signatures(source)
        assert sigs == {"add": ["a", "b"], "mul": ["x", "y"]}

    def test_syntax_error_returns_empty(self):
        """SyntaxError in source returns empty dict."""
        source = "def broken(:\n    pass\n"
        sigs = extract_function_signatures(source)
        assert sigs == {}

    def test_nested_function(self):
        """Nested function is also extracted."""
        source = (
            "def outer(a):\n"
            "    def inner(b):\n"
            "        pass\n"
        )
        sigs = extract_function_signatures(source)
        assert "outer" in sigs
        assert "inner" in sigs
        assert sigs["outer"] == ["a"]
        assert sigs["inner"] == ["b"]

    def test_self_and_cls_only(self):
        """Method with only self/cls returns empty params list."""
        source = (
            "class Foo:\n"
            "    def method(self):\n"
            "        pass\n"
        )
        sigs = extract_function_signatures(source)
        assert sigs == {"method": []}
