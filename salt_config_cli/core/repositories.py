"""Repository source configuration for Git-backed Salt content.

Repository metadata is deliberately stored separately from RaaS connection
profiles.  Secrets are never written to YAML: private-repository credentials
come from the operating-system credential helper/keychain, SSH agent, or an
explicit environment variable.
"""

from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Optional
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from salt_config_cli.core.config import discover_config_path

REPOSITORY_SCHEMA_VERSION = 1
DEFAULT_STATES_SOURCE = "vcf-salt"
DEFAULT_DATA_SOURCE = "customer-data"
_KEYRING_SERVICE = "salt-config-cli-git"


def user_repository_config_path() -> Path:
    """Return the user-level Git repository source document."""
    return Path.home() / ".scc" / "repositories.yaml"


def workspace_repository_config_path() -> Path:
    """Return the workspace-level Git repository source document."""
    return Path.cwd() / ".scc" / "repositories.yaml"


def discover_repository_config_path(
    path: Optional[str | Path] = None,
    *,
    connection_config: Optional[str | Path] = None,
    workspace: bool = False,
) -> Path:
    """Resolve an explicit, environment, workspace, or adjacent source file."""
    if path:
        return Path(path).expanduser()
    if os.getenv("SCC_REPOSITORIES_CONFIG"):
        return Path(os.environ["SCC_REPOSITORIES_CONFIG"]).expanduser()
    if workspace:
        return workspace_repository_config_path()

    connection_path = discover_config_path(connection_config)
    adjacent = connection_path.parent / "repositories.yaml"
    workspace_candidate = workspace_repository_config_path()
    if connection_config is not None:
        return adjacent
    if workspace_candidate.exists():
        return workspace_candidate
    if adjacent.exists():
        return adjacent
    return adjacent if connection_path.parent.exists() else user_repository_config_path()


def _normalise_relative_path(value: str, *, field_name: str) -> str:
    value = value.strip().replace("\\", "/") or "."
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{field_name} must be a relative path without '..'")
    return "." if str(path) in {"", "."} else str(path)


class RepositorySource(BaseModel):
    """One named Git source used for reusable states or customer data."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["states", "data"]
    url: str
    ref: str = "main"
    root: str = "."
    layout: Optional[str] = None
    auth: Literal["auto", "ssh", "credential-helper", "token"] = "auto"
    username: Optional[str] = None
    verify_tls: bool = True
    description: Optional[str] = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        value = value.strip()
        if not value or any(char in value for char in ("\n", "\r", "\0")):
            raise ValueError("repository URL is required")
        if value.startswith("-"):
            raise ValueError("repository URL must not begin with '-'")
        parsed = urlparse(value)
        if parsed.password or (parsed.scheme in {"http", "https"} and parsed.username):
            raise ValueError("repository URL must not contain embedded credentials")
        if parsed.scheme in {"http", "https"} and (parsed.query or parsed.fragment):
            raise ValueError("HTTP(S) repository URL must not contain query parameters or fragments")
        return value.rstrip("/") if not value.startswith("file://") else value

    @field_validator("ref")
    @classmethod
    def validate_ref(cls, value: str) -> str:
        value = value.strip()
        if (
            not value
            or value.startswith("-")
            or ".." in value
            or "@{" in value
            or any(ord(char) < 32 or char.isspace() for char in value)
        ):
            raise ValueError("ref must be a safe branch, tag, or commit name")
        return value

    @field_validator("root")
    @classmethod
    def validate_root(cls, value: str) -> str:
        return _normalise_relative_path(value, field_name="root")

    @field_validator("layout")
    @classmethod
    def validate_layout(cls, value: Optional[str]) -> Optional[str]:
        if value is None or not value.strip():
            return None
        cleaned = value.strip().replace("\\", "/")
        # Validate path traversal after substituting safe placeholder values.
        try:
            sample = cleaned.format(
                resource="resource",
                environment="environment",
                version="version",
                values="values",
            )
        except (KeyError, IndexError, ValueError) as exc:
            raise ValueError(f"layout is invalid: {exc}") from exc
        _normalise_relative_path(sample, field_name="layout")
        allowed = {"resource", "environment", "version", "values"}
        used = set(re.findall(r"\{([^{}]+)\}", cleaned))
        unknown = used - allowed
        if unknown:
            raise ValueError(f"layout contains unsupported placeholders: {', '.join(sorted(unknown))}")
        return cleaned


class RepositoryConfigFile(BaseModel):
    """Persistent, non-secret Git source catalog."""

    model_config = ConfigDict(extra="forbid")

    version: int = REPOSITORY_SCHEMA_VERSION
    default_states_source: Optional[str] = None
    default_data_source: Optional[str] = None
    sources: dict[str, RepositorySource] = Field(default_factory=dict)


class RepositoryStore:
    """Read/write repository sources with migration and atomic persistence."""

    def __init__(
        self,
        path: Optional[str | Path] = None,
        *,
        connection_config: Optional[str | Path] = None,
        workspace: bool = False,
    ) -> None:
        self.connection_config = discover_config_path(connection_config)
        self.path = discover_repository_config_path(
            path,
            connection_config=self.connection_config,
            workspace=workspace,
        )
        self.last_migration: Optional[str] = None

    def _legacy_sources(self) -> RepositoryConfigFile:
        """Read v0.6 git_* fields without coupling Git sources to profiles."""
        document = RepositoryConfigFile()
        if not self.connection_config.exists():
            return document
        try:
            raw = yaml.safe_load(self.connection_config.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            return document
        if not isinstance(raw, dict):
            return document

        states_url = raw.get("git_repo_url")
        if states_url:
            document.sources[DEFAULT_STATES_SOURCE] = RepositorySource(
                kind="states",
                url=str(states_url),
                ref=str(raw.get("git_branch") or "main"),
                root=str(raw.get("git_resources_path") or "vcf-infra"),
                description="Migrated reusable Salt state source",
            )
            document.default_states_source = DEFAULT_STATES_SOURCE

        data_url = raw.get("git_data_repo_url") or raw.get("git_pillar_repo_url")
        if data_url:
            document.sources[DEFAULT_DATA_SOURCE] = RepositorySource(
                kind="data",
                url=str(data_url),
                ref=str(raw.get("git_data_branch") or raw.get("git_pillar_branch") or "main"),
                root=str(raw.get("git_data_resources_path") or raw.get("git_pillar_resources_path") or "."),
                layout="{resource}/{values}.yaml",
                description="Migrated customer-specific values source",
            )
            document.default_data_source = DEFAULT_DATA_SOURCE
        return document

    def load(self, *, persist_migration: bool = True) -> RepositoryConfigFile:
        self.last_migration = None
        if not self.path.exists():
            document = self._legacy_sources()
            if document.sources:
                self.last_migration = "migrated legacy git_* settings into repositories.yaml"
                if persist_migration:
                    self.save(document)
            return document

        try:
            raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            raise ValueError(f"Unable to read repository configuration {self.path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise ValueError(f"Repository configuration {self.path} must contain a YAML mapping")
        try:
            document = RepositoryConfigFile.model_validate(raw)
        except ValidationError as exc:
            issues: list[str] = []
            for issue in exc.errors(include_url=False):
                location = ".".join(str(part) for part in issue.get("loc", ())) or "configuration"
                issues.append(f"{location}: {issue.get('msg', 'invalid value')}")
            raise ValueError(f"Invalid repository configuration in {self.path}: {'; '.join(issues)}") from exc
        self._repair_defaults(document)
        return document

    @staticmethod
    def _repair_defaults(document: RepositoryConfigFile) -> None:
        states = [name for name, source in document.sources.items() if source.kind == "states"]
        data = [name for name, source in document.sources.items() if source.kind == "data"]
        if document.default_states_source not in states:
            document.default_states_source = states[0] if states else None
        if document.default_data_source not in data:
            document.default_data_source = data[0] if data else None

    def save(self, document: RepositoryConfigFile) -> None:
        """Persist the non-secret catalog atomically with owner-only permissions."""
        self._repair_defaults(document)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.path.parent, stat.S_IRWXU)
        except OSError:
            pass
        payload = document.model_dump(mode="json", exclude_none=True)
        text = yaml.safe_dump(payload, sort_keys=False)
        temporary_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.chmod(temporary_path, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink(missing_ok=True)

    def add(self, name: str, source: RepositorySource, *, make_default: bool = False) -> None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", name):
            raise ValueError("source name must use letters, numbers, '.', '_' or '-' and be at most 64 characters")
        document = self.load()
        document.sources[name] = source
        if source.kind == "states" and (make_default or not document.default_states_source):
            document.default_states_source = name
        if source.kind == "data" and (make_default or not document.default_data_source):
            document.default_data_source = name
        self.save(document)

    def remove(self, name: str) -> RepositorySource:
        document = self.load()
        if name not in document.sources:
            raise ValueError(f"Repository source '{name}' does not exist")
        removed = document.sources.pop(name)
        self._repair_defaults(document)
        self.save(document)
        return removed

    def get(self, name: Optional[str] = None, *, kind: Optional[Literal["states", "data"]] = None) -> tuple[str, RepositorySource]:
        document = self.load()
        selected = name
        if selected is None:
            selected = document.default_states_source if kind == "states" else document.default_data_source
        if not selected or selected not in document.sources:
            available = ", ".join(sorted(document.sources)) or "none"
            label = f"{kind} " if kind else ""
            raise ValueError(f"No {label}repository source selected. Available sources: {available}")
        source = document.sources[selected]
        if kind and source.kind != kind:
            raise ValueError(f"Repository source '{selected}' is '{source.kind}', expected '{kind}'")
        return selected, source

    def set_default(self, name: str) -> None:
        document = self.load()
        source = document.sources.get(name)
        if source is None:
            raise ValueError(f"Repository source '{name}' does not exist")
        if source.kind == "states":
            document.default_states_source = name
        else:
            document.default_data_source = name
        self.save(document)


def source_env_token_name(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9]", "_", name).upper()
    return f"SCC_GIT_TOKEN_{safe}"


def get_source_token(name: str, *, kind: Optional[str] = None) -> tuple[Optional[str], str]:
    """Resolve a Git token without reading secrets from YAML."""
    specific = source_env_token_name(name)
    if os.getenv(specific):
        return os.environ[specific], specific
    legacy = "SCC_GIT_TOKEN" if kind == "states" else "SCC_GIT_DATA_TOKEN"
    if os.getenv(legacy):
        return os.environ[legacy], legacy
    try:
        import keyring

        backend = keyring.get_keyring()
        if backend.priority > 0:
            value = keyring.get_password(_KEYRING_SERVICE, name)
            if value:
                return value, "OS keychain"
    except Exception:
        pass
    return None, "none"


def set_source_token(name: str, token: str) -> bool:
    try:
        import keyring

        backend = keyring.get_keyring()
        if backend.priority <= 0:
            return False
        keyring.set_password(_KEYRING_SERVICE, name, token)
        return True
    except Exception:
        return False


def delete_source_token(name: str) -> bool:
    try:
        import keyring

        backend = keyring.get_keyring()
        if backend.priority <= 0:
            return False
        keyring.delete_password(_KEYRING_SERVICE, name)
        return True
    except Exception:
        return False


def export_non_secret_sources(document: RepositoryConfigFile) -> str:
    """Return a stable YAML representation suitable for review/approval."""
    return yaml.safe_dump(document.model_dump(mode="json", exclude_none=True), sort_keys=False)


def source_fingerprint(source: RepositorySource) -> str:
    """Stable non-secret fingerprint for the Git object cache.

    Content mapping fields such as ``root`` or ``layout`` deliberately do not
    create another clone of the same ref.
    """
    import hashlib

    payload = json.dumps({"url": source.url, "ref": source.ref}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
