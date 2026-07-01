"""Configuration loading and management."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import tomli  # For reading TOML

from terminal_ai_co_agent.config.defaults import DEFAULT_CONFIG_TOML
from terminal_ai_co_agent.config.types import CoAgentConfig
from terminal_ai_co_agent.logging.logger import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

# Configuration file search paths (in order of precedence)
CONFIG_FILE_NAMES = [
    ".coagent.toml",       # Project-local
    "coagent.toml",        # Project root
]


def _get_user_config_path() -> Path:
    """Get user-level config path."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "coagent" / "config.toml"


def _find_config_file(project_root: Path | None = None) -> Path | None:
    """Find the configuration file to load.

    Search order:
    1. COAGENT_CONFIG environment variable
    2. .coagent.toml in project root
    3. coagent.toml in project root
    4. ~/.config/coagent/config.toml (user-level)
    """
    # Explicit environment variable
    env_path = os.environ.get("COAGENT_CONFIG")
    if env_path:
        path = Path(env_path).expanduser()
        if path.exists():
            return path

    # Project-local files
    root = project_root or Path.cwd()
    for name in CONFIG_FILE_NAMES:
        path = root / name
        if path.exists():
            return path

    # User-level
    user_path = _get_user_config_path()
    if user_path.exists():
        return user_path

    return None


def _load_toml(path: Path) -> dict[str, Any]:
    """Load and parse a TOML file."""
    with open(path, "rb") as f:
        return tomli.load(f)


def load_config(
    config_path: Path | str | None = None,
    project_root: Path | None = None,
) -> CoAgentConfig:
    """Load the complete configuration.

    Priority:
    1. Explicit config_path argument
    2. File discovery (env var → project-local → user-level)
    3. Embedded defaults
    """
    # Determine which file to load
    if config_path:
        path = Path(config_path).expanduser()
    else:
        path = _find_config_file(project_root)

    # Load or use defaults
    if path and path.exists():
        logger.info("config.loading", path=str(path))
        data = _load_toml(path)
        logger.info("config.loaded", path=str(path))
    else:
        logger.info("config.defaults", message="No config file found, using defaults")
        data = tomli.loads(DEFAULT_CONFIG_TOML)

    # Validate and return
    config = CoAgentConfig(**data)
    logger.debug("config.validated", sections=list(data.keys()))
    return config


def write_default_config(path: Path) -> None:
    """Write the default configuration to a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write(DEFAULT_CONFIG_TOML)
    logger.info("config.written", path=str(path))


def resolve_path(config_path: str | Path, project_root: Path) -> Path:
    """Resolve a path relative to project root or user home."""
    path = Path(config_path)
    if path.is_absolute():
        return path
    # Expand ~
    expanded = path.expanduser()
    if expanded.is_absolute():
        return expanded
    # Relative to project root
    return (project_root / path).resolve()
