"""Agent build registry for managing multiple agent implementations."""

from typing import Dict, Type
from .base import AgentBuildBase

# Registry of available builds
_BUILDS: Dict[str, Type[AgentBuildBase]] = {}


def register_build(name: str):
    """
    Decorator to register an agent build.

    Usage:
        @register_build("v1")
        class V1Build(AgentBuildBase):
            ...
    """
    def decorator(cls: Type[AgentBuildBase]):
        _BUILDS[name] = cls
        return cls
    return decorator


def get_build(name: str) -> AgentBuildBase:
    """
    Get an instance of the named build.

    Args:
        name: Build name (e.g., "v1", "v2")

    Returns:
        Instance of the agent build

    Raises:
        ValueError: If build name is not registered
    """
    if name not in _BUILDS:
        available = list(_BUILDS.keys())
        raise ValueError(
            f"Unknown agent build: '{name}'. "
            f"Available builds: {available}"
        )
    return _BUILDS[name]()


def list_builds() -> list:
    """List all registered build names."""
    return list(_BUILDS.keys())
