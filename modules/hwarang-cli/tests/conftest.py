"""Test fixtures for hwarang-cli."""

import pytest

from hwarang_cli.tools.registry import ToolRegistry


@pytest.fixture
def tool_registry():
    """Tool registry with defaults registered."""
    registry = ToolRegistry()
    registry.register_defaults()
    return registry
