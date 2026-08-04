"""Static KB-to-Salt solution catalog models and lookup services.

The catalog is an authoritative, version-controlled mapping maintained next to
open-source Salt states. Runtime code may search and execute catalog entries,
but it never generates or mutates KB-to-SLS mappings.

The execution contract intentionally maps each KB to one existing resource SLS.
The state folder remains simple: ``<resource>.sls``, ``default.yaml`` and
``map.jinja``. Customer ``values.yaml`` data is supplied as runtime pillar and
is never copied to the RaaS file server.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Literal, Optional
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


class KBCatalogError(RuntimeError):
    """Raised when a catalog is missing, invalid, or internally inconsistent."""


class SolutionMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    description: str = ""
    status: Literal["draft", "community", "validated", "verified", "deprecated"] = "draft"
    maturity: Literal["experimental", "beta", "production", "deprecated"] = "experimental"
    maintainers: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", cleaned):
            raise ValueError("metadata.id must use lowercase letters, numbers, '.', '_' or '-'")
        return cleaned


class KBReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = "broadcom"
    id: str
    title: Optional[str] = None
    url: Optional[str] = None
    last_verified: Optional[str] = None

    @field_validator("provider", "id")
    @classmethod
    def non_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value must not be empty")
        return cleaned

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        parsed = urlparse(cleaned)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("kb.url must be an absolute HTTP(S) URL")
        return cleaned


class Applicability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    products: list[str] = Field(default_factory=lambda: ["VCF"])
    components: list[str] = Field(default_factory=list)
    versions: list[str] = Field(default_factory=list)
    symptoms: list[str] = Field(default_factory=list)
    error_patterns: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)


class ExecutionMapping(BaseModel):
    """One statically mapped reusable Salt state for a KB resolution.

    Catalog authors normally need only ``state`` and ``values_schema``. SCC
    derives the resource folder and SLS filename from the dotted state. The
    optional overrides support non-conventional repositories without making the
    common catalog format harder to understand.
    """

    model_config = ConfigDict(extra="forbid")

    state: str
    resource: Optional[str] = None
    entrypoint: Optional[str] = None
    description: str = ""
    values_schema: Optional[str] = None
    values_required: bool = True
    dry_run_supported: bool = True
    reboot_required: bool = False
    service_restart_required: bool = False

    @field_validator("state")
    @classmethod
    def validate_state(cls, value: str) -> str:
        cleaned = value.strip().strip(".")
        if not cleaned or not re.fullmatch(r"[A-Za-z0-9_.-]+", cleaned):
            raise ValueError("execution.state must be a dotted Salt state reference")
        if len(cleaned.split(".")) < 2:
            raise ValueError("execution.state must include a resource folder and SLS name")
        return cleaned

    @field_validator("resource")
    @classmethod
    def validate_resource(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip().replace("\\", "/")
        path = PurePosixPath(cleaned)
        if (
            not cleaned
            or path.is_absolute()
            or any(part in {"", ".", ".."} for part in path.parts)
            or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in path.parts)
        ):
            raise ValueError("execution.resource must be a safe relative resource path")
        return path.as_posix()

    @field_validator("entrypoint")
    @classmethod
    def validate_entrypoint(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip().replace("\\", "/")
        path = PurePosixPath(cleaned)
        if not cleaned or path.is_absolute() or ".." in path.parts or path.suffix != ".sls":
            raise ValueError("execution.entrypoint must be a safe relative .sls path")
        return path.as_posix()

    @field_validator("values_schema")
    @classmethod
    def validate_values_schema(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip().replace("\\", "/")
        path = PurePosixPath(cleaned)
        if not cleaned or path.is_absolute() or ".." in path.parts:
            raise ValueError("execution.values_schema must be a safe repository-relative path")
        return path.as_posix()

    @property
    def resolved_resource(self) -> str:
        if self.resource:
            return self.resource
        parts = self.state.split(".")
        return parts[-2]

    @property
    def resolved_entrypoint(self) -> str:
        if not self.entrypoint:
            return f"{self.state.split('.')[-1]}.sls"
        path = PurePosixPath(self.entrypoint)
        # deploy expects an entrypoint relative to the selected resource folder.
        if len(path.parts) == 1:
            return path.as_posix()
        resource_parts = PurePosixPath(self.resolved_resource).parts
        for index in range(len(path.parts)):
            if path.parts[index:index + len(resource_parts)] == resource_parts:
                suffix = path.parts[index + len(resource_parts):]
                if suffix:
                    return PurePosixPath(*suffix).as_posix()
        return path.name


class RiskDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: Literal["low", "medium", "high", "critical"] = "medium"
    impact: str = ""
    requires_confirmation: bool = True
    rollback_supported: bool = False
    rollback_state: Optional[str] = None


class KBSolution(BaseModel):
    """Full static KB solution definition."""

    model_config = ConfigDict(extra="forbid")

    api_version: str = "saltext.vcf/v1"
    kind: Literal["KBResolution"] = "KBResolution"
    metadata: SolutionMetadata
    kb: KBReference
    applicability: Applicability = Field(default_factory=Applicability)
    execution: ExecutionMapping
    risk: RiskDefinition = Field(default_factory=RiskDefinition)

    @property
    def key(self) -> str:
        return f"{self.kb.provider}:{self.kb.id}".lower()


class CatalogEntry(BaseModel):
    """Compact search index entry. Full solution content remains in solution.yaml."""

    model_config = ConfigDict(extra="allow")

    solution_id: str
    kb_id: str
    title: str
    summary: str = ""
    components: list[str] = Field(default_factory=list)
    versions: list[str] = Field(default_factory=list)
    symptoms: list[str] = Field(default_factory=list)
    status: str = "draft"
    risk: str = "medium"
    solution_path: str
    state: str

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_state_field(cls, value: Any) -> Any:
        if isinstance(value, dict) and not value.get("state"):
            legacy = value.get("remediation_states")
            if isinstance(legacy, list) and len(legacy) == 1:
                value = dict(value)
                value["state"] = legacy[0]
                value.pop("remediation_states", None)
        return value

    @field_validator("solution_path")
    @classmethod
    def safe_solution_path(cls, value: str) -> str:
        cleaned = value.strip().replace("\\", "/")
        path = PurePosixPath(cleaned)
        if not cleaned or path.is_absolute() or ".." in path.parts:
            raise ValueError("solution_path must be a safe path relative to the catalog file")
        return path.as_posix()

    @property
    def mapped_state(self) -> str:
        return self.state


class CatalogIndex(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_version: str = "saltext.vcf/catalog/v1"
    kind: Literal["KBSolutionCatalog"] = "KBSolutionCatalog"
    catalog_version: str = "1.0.0"
    solutions: list[CatalogEntry] = Field(default_factory=list)


@dataclass(frozen=True)
class LoadedCatalog:
    path: Path
    version: str
    solutions: tuple[KBSolution, ...]
    repository_root: Path


@dataclass(frozen=True)
class CatalogSearchResult:
    solution: KBSolution
    score: float
    matched_fields: tuple[str, ...]


_DEFAULT_CANDIDATES = (
    "solutions/catalog.yaml",
    "solutions/catalog.yml",
    "catalog/generated/solutions.yaml",
    "catalog/solutions.yaml",
)


class KBCatalogService:
    """Load, validate, and search static solution definitions."""

    @staticmethod
    def discover(repository_root: Path, explicit_path: Optional[str | Path] = None) -> Path:
        root = repository_root.expanduser().resolve()
        if explicit_path:
            candidate = Path(explicit_path).expanduser()
            if candidate.is_absolute():
                raise KBCatalogError("Repository catalog paths must be relative; use --catalog-file for a local absolute path")
            candidate = (root / candidate).resolve()
            try:
                candidate.relative_to(root)
            except ValueError as exc:
                raise KBCatalogError("KB catalog path must not escape the reusable-state repository") from exc
            if candidate.exists():
                return candidate
            raise KBCatalogError(f"KB catalog was not found: {candidate}")
        for relative in _DEFAULT_CANDIDATES:
            candidate = root / relative
            if candidate.is_file():
                return candidate.resolve()
        solutions_dir = root / "solutions"
        if solutions_dir.is_dir() and any(solutions_dir.glob("*/solution.y*ml")):
            return solutions_dir.resolve()
        raise KBCatalogError(
            "No KB solution catalog was found. Expected solutions/catalog.yaml or "
            "solutions/<solution-id>/solution.yaml in the reusable-state repository."
        )

    @staticmethod
    def _read_yaml(path: Path) -> dict[str, Any]:
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise KBCatalogError(f"Catalog file was not found: {path}") from exc
        except (UnicodeDecodeError, yaml.YAMLError) as exc:
            raise KBCatalogError(f"Invalid YAML in {path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise KBCatalogError(f"Catalog YAML must contain a mapping: {path}")
        return raw

    @staticmethod
    def _parse_solution(path: Path) -> KBSolution:
        raw = KBCatalogService._read_yaml(path)
        try:
            return KBSolution.model_validate(raw)
        except ValidationError as exc:
            raise KBCatalogError(f"Invalid solution definition {path}: {exc}") from exc

    def load(self, path: Path, *, repository_root: Optional[Path] = None) -> LoadedCatalog:
        source_path = path.expanduser().resolve()
        repo_root = (repository_root or source_path.parent).expanduser().resolve()
        solutions: list[KBSolution] = []
        version = "unversioned"

        if source_path.is_dir():
            files = sorted(source_path.glob("*/solution.yaml")) + sorted(source_path.glob("*/solution.yml"))
            if not files:
                raise KBCatalogError(f"No solutions/*/solution.yaml files found under {source_path}")
            solutions = [self._parse_solution(file) for file in files]
        else:
            raw = self._read_yaml(source_path)
            if raw.get("kind") == "KBResolution":
                solutions = [self._parse_solution(source_path)]
            else:
                try:
                    index = CatalogIndex.model_validate(raw)
                except ValidationError as exc:
                    raise KBCatalogError(f"Invalid catalog index {source_path}: {exc}") from exc
                version = index.catalog_version
                for entry in index.solutions:
                    candidates = [source_path.parent / entry.solution_path, repo_root / entry.solution_path]
                    solution_path = next((item for item in candidates if item.is_file()), None)
                    if solution_path is None:
                        raise KBCatalogError(
                            f"Catalog entry '{entry.solution_id}' references missing solution: {entry.solution_path}"
                        )
                    solution = self._parse_solution(solution_path)
                    if solution.metadata.id != entry.solution_id:
                        raise KBCatalogError(
                            f"Catalog entry '{entry.solution_id}' does not match metadata.id "
                            f"'{solution.metadata.id}' in {solution_path}"
                        )
                    if solution.kb.id != entry.kb_id:
                        raise KBCatalogError(
                            f"Catalog KB '{entry.kb_id}' does not match '{solution.kb.id}' in {solution_path}"
                        )
                    if entry.mapped_state != solution.execution.state:
                        raise KBCatalogError(
                            f"Catalog state for '{entry.solution_id}' is stale; expected "
                            f"'{solution.execution.state}', found '{entry.mapped_state}'"
                        )
                    if entry.title != solution.metadata.title:
                        raise KBCatalogError(f"Catalog title for '{entry.solution_id}' does not match solution.yaml")
                    if entry.status and entry.status != solution.metadata.status:
                        raise KBCatalogError(
                            f"Catalog status for '{entry.solution_id}' is '{entry.status}' but solution.yaml declares "
                            f"'{solution.metadata.status}'"
                        )
                    if set(entry.components) != set(solution.applicability.components):
                        raise KBCatalogError(f"Catalog components for '{entry.solution_id}' are stale")
                    if set(entry.versions) != set(solution.applicability.versions):
                        raise KBCatalogError(f"Catalog versions for '{entry.solution_id}' are stale")
                    solutions.append(solution)

        self._validate_uniqueness(solutions)
        return LoadedCatalog(source_path, version, tuple(solutions), repo_root)

    @staticmethod
    def _validate_uniqueness(solutions: Iterable[KBSolution]) -> None:
        solution_ids: set[str] = set()
        kb_keys: set[str] = set()
        for solution in solutions:
            if solution.metadata.id in solution_ids:
                raise KBCatalogError(f"Duplicate solution id: {solution.metadata.id}")
            if solution.key in kb_keys:
                raise KBCatalogError(f"Duplicate KB mapping: {solution.kb.provider} {solution.kb.id}")
            solution_ids.add(solution.metadata.id)
            kb_keys.add(solution.key)

    @staticmethod
    def version_matches(selected: str, patterns: Iterable[str]) -> bool:
        if not selected:
            return True
        patterns = list(patterns)
        if not patterns:
            return True
        normalized = selected.strip().lower()
        for pattern in patterns:
            candidate = pattern.strip().lower().replace("x", "*")
            if fnmatch.fnmatchcase(normalized, candidate):
                return True
        return False

    @staticmethod
    def component_matches(selected: str, components: Iterable[str]) -> bool:
        if not selected:
            return True
        normalized = selected.strip().lower()
        return any(normalized == item.strip().lower() for item in components)

    @staticmethod
    def get(catalog: LoadedCatalog, identifier: str) -> KBSolution:
        needle = identifier.strip().lower()
        matches = [
            item
            for item in catalog.solutions
            if needle
            in {
                item.metadata.id.lower(),
                item.kb.id.lower(),
                f"{item.kb.provider}:{item.kb.id}".lower(),
            }
        ]
        if not matches:
            raise KBCatalogError(f"No catalog solution matches '{identifier}'")
        if len(matches) > 1:
            raise KBCatalogError(f"Identifier '{identifier}' matches more than one solution")
        return matches[0]

    @staticmethod
    def search(
        catalog: LoadedCatalog,
        query: str = "",
        *,
        component: str = "",
        version: str = "",
        statuses: Optional[set[str]] = None,
    ) -> list[CatalogSearchResult]:
        tokens = {token for token in re.findall(r"[a-z0-9_.-]+", query.lower()) if len(token) > 1}
        results: list[CatalogSearchResult] = []
        for solution in catalog.solutions:
            if statuses and solution.metadata.status not in statuses:
                continue
            if component and not KBCatalogService.component_matches(component, solution.applicability.components):
                continue
            if version and not KBCatalogService.version_matches(version, solution.applicability.versions):
                continue

            fields = {
                "kb": " ".join([solution.kb.id, solution.kb.title or "", solution.metadata.title]).lower(),
                "summary": " ".join([solution.metadata.description, *solution.metadata.tags]).lower(),
                "components": " ".join(solution.applicability.components).lower(),
                "symptoms": " ".join(solution.applicability.symptoms).lower(),
                "errors": " ".join(solution.applicability.error_patterns).lower(),
                "states": solution.execution.state.lower(),
            }
            if not tokens:
                results.append(CatalogSearchResult(solution, 1.0, ()))
                continue
            weights = {"kb": 4.0, "symptoms": 3.0, "errors": 3.0, "components": 2.0, "summary": 1.5, "states": 1.0}
            score = 0.0
            matched: list[str] = []
            for name, text in fields.items():
                hits = sum(1 for token in tokens if token in text)
                if hits:
                    score += hits * weights[name]
                    matched.append(name)
            if score:
                results.append(CatalogSearchResult(solution, score, tuple(matched)))
        return sorted(results, key=lambda item: (-item.score, item.solution.kb.id))

    @staticmethod
    def validate_state_references(catalog: LoadedCatalog) -> list[str]:
        """Verify the single mapped SLS and optional values schema resolve in Git."""
        errors: list[str] = []
        root = catalog.repository_root
        for solution in catalog.solutions:
            execution = solution.execution
            if execution.values_schema:
                schema_path = root / execution.values_schema
                if not schema_path.is_file():
                    errors.append(
                        f"{solution.metadata.id}: values schema does not exist ({execution.values_schema})"
                    )

            state_path = root / (execution.state.replace(".", "/") + ".sls")
            init_path = root / execution.state.replace(".", "/") / "init.sls"
            mapped_file = state_path if state_path.is_file() else init_path if init_path.is_file() else None
            if mapped_file is None:
                errors.append(
                    f"{solution.metadata.id}: state '{execution.state}' does not exist "
                    f"({state_path.relative_to(root)})"
                )
                continue

            if execution.entrypoint:
                entrypoint_path = PurePosixPath(execution.entrypoint)
                candidates = [root / entrypoint_path]
                if len(entrypoint_path.parts) == 1:
                    resource = PurePosixPath(execution.resolved_resource)
                    candidates.extend([
                        root / resource / entrypoint_path,
                        root / "vcf-infra" / resource / entrypoint_path,
                        root / "states" / resource / entrypoint_path,
                    ])
                entrypoint_file = next((candidate for candidate in candidates if candidate.is_file()), None)
                if entrypoint_file is None:
                    errors.append(
                        f"{solution.metadata.id}: entrypoint '{execution.entrypoint}' was not found"
                    )
                elif entrypoint_file.resolve() != mapped_file.resolve():
                    errors.append(
                        f"{solution.metadata.id}: state '{execution.state}' and entrypoint "
                        f"'{execution.entrypoint}' resolve to different files"
                    )
        return errors
