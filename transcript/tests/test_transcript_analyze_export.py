"""Tests for export command: SAN-10."""
import argparse
import json
import shutil
import pytest
from pathlib import Path

from conftest import load_analyzer, load_compactor


class TestExportCommand:
    """Tests for export command delegating to compactor."""

    def test_export_default_level(self, sample_1mb_path, tmp_path):
        """Export with default level (l2-compact), verify output file created."""
        mod = load_analyzer()
        # Copy sample to tmp_path so output goes there
        work_file = tmp_path / sample_1mb_path.name
        shutil.copy2(sample_1mb_path, work_file)

        data = mod.load_session(str(work_file))
        args = argparse.Namespace(level="l2-compact")
        mod.cmd_export(data, str(work_file), args)

        expected_output = work_file.with_suffix(".l2c.json")
        assert expected_output.exists(), f"Expected output at {expected_output}"

    def test_export_level_3(self, sample_1mb_path, tmp_path):
        """Export with --level 3, verify output file with .l3.json suffix."""
        mod = load_analyzer()
        work_file = tmp_path / sample_1mb_path.name
        shutil.copy2(sample_1mb_path, work_file)

        data = mod.load_session(str(work_file))
        args = argparse.Namespace(level="3")
        mod.cmd_export(data, str(work_file), args)

        expected_output = work_file.with_suffix(".l3.json")
        assert expected_output.exists(), f"Expected output at {expected_output}"

    def test_export_output_valid_json(self, sample_1mb_path, tmp_path):
        """Verify exported file is valid JSON."""
        mod = load_analyzer()
        work_file = tmp_path / sample_1mb_path.name
        shutil.copy2(sample_1mb_path, work_file)

        data = mod.load_session(str(work_file))
        args = argparse.Namespace(level="l2-compact")
        mod.cmd_export(data, str(work_file), args)

        output_path = work_file.with_suffix(".l2c.json")
        with open(output_path) as f:
            result = json.load(f)
        assert isinstance(result, dict)
        assert "slim_level" in result

    def test_export_output_smaller(self, sample_1mb_path, tmp_path):
        """Verify exported file is smaller than original."""
        mod = load_analyzer()
        work_file = tmp_path / sample_1mb_path.name
        shutil.copy2(sample_1mb_path, work_file)

        data = mod.load_session(str(work_file))
        args = argparse.Namespace(level="l2-compact")
        mod.cmd_export(data, str(work_file), args)

        output_path = work_file.with_suffix(".l2c.json")
        original_size = work_file.stat().st_size
        output_size = output_path.stat().st_size
        assert output_size < original_size, (
            f"Output ({output_size}) should be smaller than original ({original_size})"
        )

    @pytest.mark.slow
    def test_export_75mb(self, sample_75mb_path, tmp_path):
        """Export 75MB sample, verify it completes and produces output."""
        mod = load_analyzer()
        work_file = tmp_path / sample_75mb_path.name
        shutil.copy2(sample_75mb_path, work_file)

        data = mod.load_session(str(work_file))
        args = argparse.Namespace(level="l2-compact")
        mod.cmd_export(data, str(work_file), args)

        expected_output = work_file.with_suffix(".l2c.json")
        assert expected_output.exists()
        assert expected_output.stat().st_size > 0
