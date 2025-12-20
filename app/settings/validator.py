# app/settings/validator.py
"""
Extensible settings validator that validates YAML sections against inferred schemas.

The validator works by:
1. Inferring the schema from the existing settings structure
2. Allowing custom validators to be registered for specific sections
3. Validating that new values match the expected structure and types
"""

import yaml
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

LOGGER = logging.getLogger(__name__)


@dataclass
class ValidationError:
    """Represents a single validation error."""
    path: str  # Dot-separated path to the problematic field
    message: str
    value: Any = None

    def __str__(self) -> str:
        if self.path:
            return f"{self.path}: {self.message}"
        return self.message


@dataclass
class ValidationResult:
    """Result of a validation operation."""
    is_valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    parsed_value: Any = None

    def __bool__(self) -> bool:
        return self.is_valid

    @property
    def error_messages(self) -> list[str]:
        return [str(e) for e in self.errors]

    @property
    def first_error(self) -> Optional[str]:
        return str(self.errors[0]) if self.errors else None


# Type alias for custom validator functions
# Validators receive (value, reference_schema) and return ValidationResult
CustomValidator = Callable[[Any, Any], ValidationResult]


class SettingsValidator:
    """
    Validates settings sections against inferred or custom schemas.

    The validator is extensible - you can register custom validators for
    specific section keys that need special handling.
    """

    # Class-level registry of custom validators
    _custom_validators: dict[str, CustomValidator] = {}

    # Known types that should be validated strictly
    STRICT_TYPES = (str, int, float, bool)

    @classmethod
    def register_validator(cls, section_key: str, validator: CustomValidator) -> None:
        """
        Register a custom validator for a specific settings section.

        Args:
            section_key: The top-level key this validator handles (e.g., 'models')
            validator: A callable that takes (value, reference) and returns ValidationResult
        """
        cls._custom_validators[section_key] = validator
        LOGGER.debug(f"Registered custom validator for section: {section_key}")

    @classmethod
    def validate_yaml_string(cls, yaml_string: str, reference: Any = None) -> ValidationResult:
        """
        Validate a YAML string can be parsed and optionally matches a reference structure.

        Args:
            yaml_string: The YAML content to validate
            reference: Optional reference value to validate structure against

        Returns:
            ValidationResult with parsed value if valid
        """
        # First, try to parse the YAML
        try:
            parsed = yaml.safe_load(yaml_string)
        except yaml.YAMLError as e:
            error_msg = str(e)
            # Extract line number if available
            if hasattr(e, 'problem_mark') and e.problem_mark:
                line = e.problem_mark.line + 1
                col = e.problem_mark.column + 1
                error_msg = f"Line {line}, column {col}: {e.problem}"
            return ValidationResult(
                is_valid=False,
                errors=[ValidationError(path="", message=f"Invalid YAML syntax: {error_msg}")]
            )

        # If no reference provided, just check it parses
        if reference is None:
            return ValidationResult(is_valid=True, parsed_value=parsed)

        # Validate structure against reference
        return cls.validate_structure(parsed, reference)

    @classmethod
    def validate_section(
        cls,
        section_key: str,
        yaml_string: str,
        reference_settings: dict
    ) -> ValidationResult:
        """
        Validate a specific settings section.

        Args:
            section_key: The section being validated (e.g., 'models', 'search')
            yaml_string: The YAML content for this section
            reference_settings: The full reference settings dict

        Returns:
            ValidationResult with the parsed section if valid
        """
        # First parse the YAML
        parse_result = cls.validate_yaml_string(yaml_string)
        if not parse_result.is_valid:
            return parse_result

        parsed = parse_result.parsed_value

        # Check for custom validator
        if section_key in cls._custom_validators:
            reference = reference_settings.get(section_key)
            return cls._custom_validators[section_key](parsed, reference)

        # Get reference for this section
        reference = reference_settings.get(section_key)

        # If no reference exists, allow any valid YAML
        if reference is None:
            return ValidationResult(is_valid=True, parsed_value=parsed)

        # Validate structure matches reference
        return cls.validate_structure(parsed, reference, section_key)

    @classmethod
    def validate_structure(
        cls,
        value: Any,
        reference: Any,
        path: str = ""
    ) -> ValidationResult:
        """
        Recursively validate that a value matches the structure of a reference.

        This is a permissive validator that:
        - Allows extra keys in dicts (for extensibility)
        - Validates types match for scalar values
        - Recursively validates nested structures

        Args:
            value: The value to validate
            reference: The reference value to match structure against
            path: Current path for error messages

        Returns:
            ValidationResult
        """
        errors: list[ValidationError] = []

        # Handle None values
        if value is None and reference is not None:
            # Allow None if reference was a dict/list (clearing a section)
            if isinstance(reference, (dict, list)):
                return ValidationResult(is_valid=True, parsed_value=value)
            errors.append(ValidationError(
                path=path,
                message=f"Expected {type(reference).__name__}, got null",
                value=value
            ))
            return ValidationResult(is_valid=False, errors=errors)

        # If reference is None, allow anything
        if reference is None:
            return ValidationResult(is_valid=True, parsed_value=value)

        # Validate dicts
        if isinstance(reference, dict):
            if not isinstance(value, dict):
                errors.append(ValidationError(
                    path=path,
                    message=f"Expected a mapping/object, got {type(value).__name__}",
                    value=value
                ))
                return ValidationResult(is_valid=False, errors=errors)

            # Recursively validate each key that exists in both
            for key in value:
                child_path = f"{path}.{key}" if path else key
                if key in reference:
                    child_result = cls.validate_structure(
                        value[key],
                        reference[key],
                        child_path
                    )
                    if not child_result.is_valid:
                        errors.extend(child_result.errors)
                # Extra keys are allowed (extensibility)

            return ValidationResult(
                is_valid=len(errors) == 0,
                errors=errors,
                parsed_value=value
            )

        # Validate lists
        if isinstance(reference, list):
            if not isinstance(value, list):
                errors.append(ValidationError(
                    path=path,
                    message=f"Expected a list, got {type(value).__name__}",
                    value=value
                ))
                return ValidationResult(is_valid=False, errors=errors)

            # If reference has items, validate each item against first reference item
            if reference and value:
                ref_item = reference[0]
                for i, item in enumerate(value):
                    child_path = f"{path}[{i}]"
                    child_result = cls.validate_structure(item, ref_item, child_path)
                    if not child_result.is_valid:
                        errors.extend(child_result.errors)

            return ValidationResult(
                is_valid=len(errors) == 0,
                errors=errors,
                parsed_value=value
            )

        # Validate scalar types
        if isinstance(reference, cls.STRICT_TYPES):
            # Allow type coercion for numbers
            if isinstance(reference, (int, float)) and isinstance(value, (int, float)):
                return ValidationResult(is_valid=True, parsed_value=value)

            # Otherwise check exact type
            if not isinstance(value, type(reference)):
                errors.append(ValidationError(
                    path=path,
                    message=f"Expected {type(reference).__name__}, got {type(value).__name__}",
                    value=value
                ))
                return ValidationResult(is_valid=False, errors=errors)

        return ValidationResult(is_valid=True, parsed_value=value)


# ============================================================================
# Built-in Custom Validators for Specific Sections
# ============================================================================

def _validate_model_config(model_config: Any, path: str, errors: list[ValidationError]) -> None:
    """Helper to validate a single model configuration entry."""
    if not isinstance(model_config, dict):
        errors.append(ValidationError(
            path=path,
            message="Model configuration must be a mapping"
        ))
        return

    # Check for required 'name' field
    if 'name' not in model_config:
        errors.append(ValidationError(
            path=path,
            message="Model configuration must have a 'name' field"
        ))

    # Validate context_length if present
    if 'context_length' in model_config:
        ctx = model_config['context_length']
        if not isinstance(ctx, int) or ctx <= 0:
            errors.append(ValidationError(
                path=f"{path}.context_length",
                message="context_length must be a positive integer"
            ))

    # Validate provider if present
    if 'provider' in model_config:
        provider = model_config['provider']
        valid_providers = ['ollama_chat', 'ollama', 'openai', 'anthropic', 'litellm']
        if provider not in valid_providers:
            errors.append(ValidationError(
                path=f"{path}.provider",
                message=f"Invalid provider. Must be one of: {', '.join(valid_providers)}"
            ))


def validate_models_section(value: Any, reference: Any) -> ValidationResult:
    """
    Custom validator for the 'models' section with model-specific rules.

    Structure:
        models:
          default:        # Default model config
            name: "..."
            provider: "..."
            context_length: 128000
          agent:          # Default for all agents
            name: "..."
          extractor:      # For memory extraction
            name: "..."
          agents:         # Per-agent overrides
            user_proxy_agent:
              name: "..."
            prime_agent:
              name: "..."
    """
    errors: list[ValidationError] = []

    if not isinstance(value, dict):
        return ValidationResult(
            is_valid=False,
            errors=[ValidationError("", "Models section must be a mapping")]
        )

    # Validate each top-level model entry
    for model_key, model_config in value.items():
        if model_key == 'agents':
            # Handle the nested agents subsection
            if not isinstance(model_config, dict):
                errors.append(ValidationError(
                    path="agents",
                    message="agents subsection must be a mapping"
                ))
                continue

            # Validate each agent's model config
            for agent_name, agent_model_config in model_config.items():
                _validate_model_config(
                    agent_model_config,
                    f"agents.{agent_name}",
                    errors
                )
        else:
            # Regular model config (default, agent, extractor, etc.)
            _validate_model_config(model_config, model_key, errors)

    return ValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        parsed_value=value
    )


def validate_search_section(value: Any, reference: Any) -> ValidationResult:
    """Custom validator for the 'search' section."""
    errors: list[ValidationError] = []

    if not isinstance(value, dict):
        return ValidationResult(
            is_valid=False,
            errors=[ValidationError("", "Search section must be a mapping")]
        )

    # Validate provider
    if 'provider' in value:
        valid_providers = ['brave', 'google', 'duckduckgo', 'serper']
        if value['provider'] not in valid_providers:
            errors.append(ValidationError(
                path="provider",
                message=f"Invalid search provider. Must be one of: {', '.join(valid_providers)}"
            ))

    return ValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        parsed_value=value
    )


def validate_mcp_servers_section(value: Any, reference: Any) -> ValidationResult:
    """Custom validator for the 'mcp_servers' section."""
    errors: list[ValidationError] = []

    if not isinstance(value, dict):
        return ValidationResult(
            is_valid=False,
            errors=[ValidationError("", "MCP servers section must be a mapping")]
        )

    for server_name, server_config in value.items():
        if not isinstance(server_config, dict):
            errors.append(ValidationError(
                path=server_name,
                message="MCP server configuration must be a mapping"
            ))
            continue

        # Check server type
        server_type = server_config.get('type', 'stdio')

        if server_type == 'http':
            # HTTP servers need a url
            if 'url' not in server_config:
                errors.append(ValidationError(
                    path=server_name,
                    message="HTTP MCP server must have a 'url' field"
                ))
        else:
            # stdio servers need a command
            if 'command' not in server_config:
                errors.append(ValidationError(
                    path=server_name,
                    message="MCP server must have a 'command' field"
                ))

    return ValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        parsed_value=value
    )


def validate_agent_prompts_section(value: Any, reference: Any) -> ValidationResult:
    """Custom validator for the 'agent_prompts' section."""
    errors: list[ValidationError] = []

    if not isinstance(value, dict):
        return ValidationResult(
            is_valid=False,
            errors=[ValidationError("", "Agent prompts section must be a mapping")]
        )

    for agent_name, prompt in value.items():
        if not isinstance(prompt, str):
            errors.append(ValidationError(
                path=agent_name,
                message="Agent prompt must be a string"
            ))
            continue

        if len(prompt.strip()) < 10:
            errors.append(ValidationError(
                path=agent_name,
                message="Agent prompt appears too short (less than 10 characters)"
            ))

    return ValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        parsed_value=value
    )


# Register built-in validators
SettingsValidator.register_validator('models', validate_models_section)
SettingsValidator.register_validator('search', validate_search_section)
SettingsValidator.register_validator('mcp_servers', validate_mcp_servers_section)
SettingsValidator.register_validator('agent_prompts', validate_agent_prompts_section)
