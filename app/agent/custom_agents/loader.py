# app/agent/custom_agents/loader.py
"""
Agent file discovery and loading.

This module handles:
- Finding agent YAML files in the agents/ directory
- Parsing and validating agent configurations
- Providing detailed error messages for invalid configs
"""

import os
import glob
import yaml
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from pydantic import ValidationError as PydanticValidationError

from app.agent.custom_agents.schema import CustomAgentSchema

LOGGER = logging.getLogger(__name__)

# Project root is ../../../ from this file
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


def get_agents_directory() -> Path:
    """Get the path to the agents/ directory."""
    return _PROJECT_ROOT / "agents"


@dataclass
class AgentLoadError:
    """Represents an error loading a specific agent file."""

    file_path: Path
    error_type: str  # 'yaml_syntax', 'validation', 'io'
    message: str
    details: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        base = f"{self.file_path.name}: {self.message}"
        if self.details:
            details_str = "\n  - ".join(self.details)
            return f"{base}\n  - {details_str}"
        return base


@dataclass
class AgentLoadResult:
    """Result of loading agents from the directory."""

    agents: list[CustomAgentSchema]
    errors: list[AgentLoadError]

    @property
    def successful_count(self) -> int:
        return len(self.agents)

    @property
    def failed_count(self) -> int:
        return len(self.errors)

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0


def load_agent_from_file(file_path: Path) -> tuple[Optional[CustomAgentSchema], Optional[AgentLoadError]]:
    """
    Load and validate a single agent YAML file.

    Args:
        file_path: Path to the YAML file

    Returns:
        Tuple of (agent_schema, error) - one will be None
    """
    # Skip files starting with underscore (templates/disabled)
    if file_path.name.startswith("_"):
        LOGGER.debug(f"Skipping disabled agent file: {file_path.name}")
        return None, None

    # Read the file
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except IOError as e:
        return None, AgentLoadError(
            file_path=file_path,
            error_type="io",
            message=f"Could not read file: {e}",
        )

    # Parse YAML
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        error_msg = str(e)
        if hasattr(e, "problem_mark") and e.problem_mark:
            line = e.problem_mark.line + 1
            col = e.problem_mark.column + 1
            error_msg = f"Line {line}, column {col}: {getattr(e, 'problem', 'syntax error')}"
        return None, AgentLoadError(
            file_path=file_path,
            error_type="yaml_syntax",
            message=f"Invalid YAML: {error_msg}",
        )

    if data is None:
        return None, AgentLoadError(
            file_path=file_path,
            error_type="validation",
            message="File is empty or contains only comments",
        )

    # Validate with Pydantic
    try:
        agent = CustomAgentSchema(**data)
    except PydanticValidationError as e:
        details = []
        for error in e.errors():
            loc = ".".join(str(x) for x in error["loc"])
            msg = error["msg"]
            details.append(f"{loc}: {msg}")
        return None, AgentLoadError(
            file_path=file_path,
            error_type="validation",
            message="Validation failed",
            details=details,
        )

    # Check if agent is disabled
    if not agent.enabled:
        LOGGER.info(f"Agent '{agent.name}' is disabled, skipping")
        return None, None

    LOGGER.info(f"Loaded agent '{agent.name}' from {file_path.name}")
    return agent, None


def load_custom_agents() -> AgentLoadResult:
    """
    Load all custom agents from the agents/ directory.

    Returns:
        AgentLoadResult with loaded agents and any errors
    """
    agents_dir = get_agents_directory()
    agents: list[CustomAgentSchema] = []
    errors: list[AgentLoadError] = []

    if not agents_dir.exists():
        LOGGER.warning(f"Agents directory does not exist: {agents_dir}")
        return AgentLoadResult(agents=[], errors=[])

    # Find all YAML files
    yaml_files = list(agents_dir.glob("*.yaml")) + list(agents_dir.glob("*.yml"))

    if not yaml_files:
        LOGGER.info("No agent YAML files found in agents/ directory")
        return AgentLoadResult(agents=[], errors=[])

    LOGGER.info(f"Found {len(yaml_files)} agent file(s) in {agents_dir}")

    # Track agent names to detect duplicates
    seen_names: dict[str, Path] = {}

    for file_path in sorted(yaml_files):
        agent, error = load_agent_from_file(file_path)

        if error:
            errors.append(error)
            continue

        if agent is None:
            # Disabled or skipped file
            continue

        # Check for duplicate names
        if agent.name in seen_names:
            errors.append(AgentLoadError(
                file_path=file_path,
                error_type="validation",
                message=f"Duplicate agent name '{agent.name}'",
                details=[f"Already defined in: {seen_names[agent.name].name}"],
            ))
            continue

        seen_names[agent.name] = file_path
        agents.append(agent)

    LOGGER.info(
        f"Loaded {len(agents)} agent(s), {len(errors)} error(s)"
    )

    return AgentLoadResult(agents=agents, errors=errors)


def validate_agent_yaml(yaml_content: str) -> tuple[Optional[CustomAgentSchema], Optional[str]]:
    """
    Validate agent YAML content (for use in creation tools).

    Args:
        yaml_content: Raw YAML string

    Returns:
        Tuple of (agent_schema, error_message) - one will be None
    """
    try:
        data = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        return None, f"Invalid YAML syntax: {e}"

    if data is None:
        return None, "YAML content is empty"

    try:
        agent = CustomAgentSchema(**data)
        return agent, None
    except PydanticValidationError as e:
        errors = []
        for error in e.errors():
            loc = ".".join(str(x) for x in error["loc"])
            msg = error["msg"]
            errors.append(f"{loc}: {msg}")
        return None, "Validation errors:\n" + "\n".join(f"  - {e}" for e in errors)
