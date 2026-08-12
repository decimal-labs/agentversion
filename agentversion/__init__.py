"""AgentVersion — reference implementation.

An open specification for versioning agent runtimes and keeping datasets valid.
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("agentversion")
except PackageNotFoundError:  # editable install before metadata is registered
    __version__ = "0.0.0+unknown"

from agentversion.a2a import manifest_to_agent_card
from agentversion.constants import SPEC_VERSION
from agentversion.contract import contract_from_components
from agentversion.diff import (
    COMPONENT_TYPE_TO_SURFACE,
    SURFACE_KEYS,
    surface_key_for_component,
)
from agentversion.hasher import hash_manifest, hash_surface
from agentversion.manifest import AgentManifest
from agentversion.validator import (
    ValidationResult,
    validate_manifest,
    validate_manifest_file,
)

__all__ = [
    "COMPONENT_TYPE_TO_SURFACE",
    "SPEC_VERSION",
    "SURFACE_KEYS",
    "AgentManifest",
    "ValidationResult",
    "contract_from_components",
    "hash_manifest",
    "hash_surface",
    "manifest_to_agent_card",
    "surface_key_for_component",
    "validate_manifest",
    "validate_manifest_file",
]
