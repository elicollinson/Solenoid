# app/settings/manager.py
"""
Settings manager for loading, validating, and saving application settings.

This module provides a high-level interface for settings operations,
coordinating between the config loader and the validator.
"""

import yaml
import logging
from typing import Any, Optional
from dataclasses import dataclass
from pathlib import Path

from resources.backend_config import get_settings_path
from app.agent.config import load_settings, clear_settings_cache
from app.settings.validator import SettingsValidator, ValidationResult

LOGGER = logging.getLogger(__name__)


@dataclass
class SectionInfo:
    """Information about a settings section."""
    key: str
    display_name: str
    description: str


# Define section metadata for the UI
SECTION_INFO: dict[str, SectionInfo] = {
    "models": SectionInfo(
        key="models",
        display_name="Models",
        description="Configure model settings (defaults and per-agent overrides)"
    ),
    "search": SectionInfo(
        key="search",
        display_name="Search",
        description="Configure web search provider and API keys"
    ),
    "mcp_servers": SectionInfo(
        key="mcp_servers",
        display_name="MCP Servers",
        description="Configure Model Context Protocol server connections"
    ),
    "agent_prompts": SectionInfo(
        key="agent_prompts",
        display_name="Agent Prompts",
        description="Configure system prompts for each agent"
    ),
}


class SettingsManager:
    """
    High-level manager for application settings.

    Provides methods to:
    - Get current settings
    - Get/update individual sections
    - Validate changes before saving
    - Persist changes to disk
    """

    def __init__(self):
        """
        Initialize the settings manager.

        Uses the unified settings path from backend_config, which resolves
        to local development settings or platform-specific config directory.
        """
        self._settings_path: Path = get_settings_path()

    @property
    def settings_path(self) -> Path:
        """Get the current settings file path."""
        return self._settings_path

    def get_settings(self) -> dict:
        """Get the current settings, reloading from disk."""
        clear_settings_cache()
        return load_settings()

    def get_section_keys(self) -> list[str]:
        """Get list of available section keys from current settings."""
        settings = self.get_settings()
        return list(settings.keys())

    def get_section_info(self, key: str) -> SectionInfo:
        """Get display information for a section."""
        if key in SECTION_INFO:
            return SECTION_INFO[key]
        # Generate default info for unknown sections
        return SectionInfo(
            key=key,
            display_name=key.replace("_", " ").title(),
            description=f"Configure {key} settings"
        )

    def get_all_sections_info(self) -> list[SectionInfo]:
        """Get info for all sections in current settings."""
        return [self.get_section_info(key) for key in self.get_section_keys()]

    def get_section(self, key: str) -> Any:
        """Get a specific section's value."""
        settings = self.get_settings()
        return settings.get(key)

    def get_section_as_yaml(self, key: str) -> str:
        """Get a section's value formatted as YAML string."""
        value = self.get_section(key)
        if value is None:
            return ""
        return yaml.dump(value, default_flow_style=False, allow_unicode=True, sort_keys=False)

    def validate_section(self, key: str, yaml_string: str) -> ValidationResult:
        """
        Validate a section's YAML before saving.

        Args:
            key: The section key
            yaml_string: The new YAML content for the section

        Returns:
            ValidationResult indicating if the content is valid
        """
        reference_settings = self.get_settings()
        return SettingsValidator.validate_section(key, yaml_string, reference_settings)

    def update_section(self, key: str, yaml_string: str) -> ValidationResult:
        """
        Update a section with new YAML content.

        Validates the content before saving. If validation fails,
        no changes are made to the settings file.

        Args:
            key: The section key to update
            yaml_string: The new YAML content

        Returns:
            ValidationResult - check is_valid before assuming success
        """
        # Validate first
        result = self.validate_section(key, yaml_string)
        if not result.is_valid:
            return result

        # Load current settings, update section, and save
        try:
            settings = self.get_settings()
            settings[key] = result.parsed_value
            self._save_settings(settings)

            # Clear cache so next load picks up changes
            clear_settings_cache()

            LOGGER.info(f"Successfully updated settings section: {key}")
            return result

        except Exception as e:
            LOGGER.error(f"Error saving settings: {e}")
            from app.settings.validator import ValidationError
            return ValidationResult(
                is_valid=False,
                errors=[ValidationError(path="", message=f"Failed to save: {str(e)}")]
            )

    def _save_settings(self, settings: dict) -> None:
        """
        Save settings dict to the YAML file.

        Args:
            settings: The complete settings dict to save
        """
        settings_path = str(self._settings_path)
        backup_path = settings_path + ".bak"

        # Create backup first
        if self._settings_path.exists():
            with open(self._settings_path, 'r') as f:
                backup_content = f.read()
            with open(backup_path, 'w') as f:
                f.write(backup_content)
            LOGGER.debug(f"Created backup at {backup_path}")

        # Write new settings
        with open(self._settings_path, 'w') as f:
            yaml.dump(
                settings,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
                width=120
            )

        LOGGER.info(f"Saved settings to {self._settings_path}")

    def restore_backup(self) -> bool:
        """
        Restore settings from the backup file.

        Returns:
            True if backup was restored, False if no backup exists
        """
        backup_path = Path(str(self._settings_path) + ".bak")
        if not backup_path.exists():
            return False

        with open(backup_path, 'r') as f:
            backup_content = f.read()

        with open(self._settings_path, 'w') as f:
            f.write(backup_content)

        clear_settings_cache()
        LOGGER.info("Restored settings from backup")
        return True


# Global singleton instance
_manager: Optional[SettingsManager] = None


def get_settings_manager() -> SettingsManager:
    """Get the global settings manager instance."""
    global _manager
    if _manager is None:
        _manager = SettingsManager()
    return _manager
