"""Tests for pagination helper: SAN-11."""
import argparse

import pytest

from conftest import load_analyzer


def _make_args(offset=0, limit=20, all_flag=False):
    return argparse.Namespace(offset=offset, limit=limit, all=all_flag)


class TestPagination:
    """SAN-11: pagination with --offset, --limit, --all."""

    def test_default_limit_20(self):
        mod = load_analyzer()
        items = list(range(50))
        args = _make_args()
        page, footer = mod.paginate(items, args, "analyzer sample.json errors")
        assert len(page) == 20
        assert page == list(range(20))
        assert "20 of 50" in footer

    def test_offset(self):
        mod = load_analyzer()
        items = list(range(50))
        args = _make_args(offset=10)
        page, footer = mod.paginate(items, args, "analyzer sample.json errors")
        assert len(page) == 20
        assert page == list(range(10, 30))

    def test_limit(self):
        mod = load_analyzer()
        items = list(range(50))
        args = _make_args(limit=5)
        page, footer = mod.paginate(items, args, "analyzer sample.json errors")
        assert len(page) == 5
        assert page == list(range(5))
        assert "5 of 50" in footer

    def test_offset_and_limit(self):
        mod = load_analyzer()
        items = list(range(50))
        args = _make_args(offset=10, limit=5)
        page, footer = mod.paginate(items, args, "analyzer sample.json errors")
        assert len(page) == 5
        assert page == list(range(10, 15))

    def test_all_flag(self):
        mod = load_analyzer()
        items = list(range(50))
        args = _make_args(all_flag=True)
        page, footer = mod.paginate(items, args, "analyzer sample.json errors")
        assert len(page) == 50
        assert "50 of 50" in footer

    def test_footer_has_next_command(self):
        mod = load_analyzer()
        items = list(range(50))
        args = _make_args(limit=10)
        page, footer = mod.paginate(items, args, "analyzer sample.json errors")
        assert "--offset 10" in footer

    def test_footer_no_next_when_complete(self):
        mod = load_analyzer()
        items = list(range(5))
        args = _make_args(limit=20)
        page, footer = mod.paginate(items, args, "analyzer sample.json errors")
        assert "Next:" not in footer

    def test_empty_list(self):
        mod = load_analyzer()
        items = []
        args = _make_args()
        page, footer = mod.paginate(items, args, "analyzer sample.json errors")
        assert len(page) == 0
        assert "0 of 0" in footer
