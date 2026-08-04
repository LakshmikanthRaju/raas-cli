"""Generic Git and content-workspace services.

The implementation intentionally uses the system ``git`` executable instead of
GitHub-specific raw URLs.  This supports GitHub, GitHub Enterprise, GitLab,
Bitbucket, SSH, local mirrors, tags, branches, and immutable commit SHAs while
reusing the user's established credential helper or SSH agent.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Iterator, Optional, Sequence

import yaml

from salt_config_cli.core.repositories import (
    RepositorySource,
    get_source_token,
    source_fingerprint,
)

_MAX_FILE_SIZE = 10 * 1024 * 1024
_MAX_PACKAGE_SIZE = 100 * 1024 * 1024


class GitRepositoryError(RuntimeError):
    """Actionable repository or content packaging failure."""


@dataclass(frozen=True)
class SyncedRepository:
    name: str
    source: RepositorySource
    path: Path
    commit: str
    committed_at: str
    credential_source: str = "none"


@dataclass(frozen=True)
class ContentFile:
    """One validated file in a locally assembled deployment package."""

    file_type: str
    path: str
    sha256: str
    size: int


@dataclass(frozen=True)
class ContentPackage:
    """Validated Git content ready for plan, publication, or execution.

    Package metadata is kept in memory and shown to the user. SCC deliberately
    does not create or require a separate approval manifest; Git review and
    branch/tag policy remain the customer's approval mechanism.
    """

    resource: str
    workspace: Path
    states_dir: Path
    state_entrypoint: str
    states_source: SyncedRepository
    states_repository_path: str
    environment: str = ""
    version: str = ""
    values: str = ""
    data_file: Optional[Path] = None
    data_source: Optional[SyncedRepository] = None
    data_repository_path: Optional[str] = None
    files: tuple[ContentFile, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CommandResult:
    args: tuple[str, ...]
    stdout: str
    stderr: str


class _FileLock:
    """Small cross-process lock with stale-lock recovery.

    A killed SCC process must not permanently block future repository syncs.
    On platforms where PID probing is available, dead owners are removed
    immediately; otherwise an old lock is considered stale after five minutes.
    """

    def __init__(self, path: Path, timeout: float = 30.0, stale_after: float = 300.0) -> None:
        self.path = path
        self.timeout = timeout
        self.stale_after = stale_after
        self.fd: Optional[int] = None

    @staticmethod
    def _pid_is_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return True
        return True

    def _remove_stale_lock(self) -> bool:
        try:
            age = time.time() - self.path.stat().st_mtime
            text = self.path.read_text(encoding="ascii", errors="ignore").strip()
            pid = int(text) if text.isdigit() else -1
        except (OSError, ValueError):
            return False
        if pid > 0:
            if self._pid_is_alive(pid):
                return False
        elif age <= self.stale_after:
            return False
        try:
            self.path.unlink()
            return True
        except FileNotFoundError:
            return True
        except OSError:
            return False

    def __enter__(self) -> "_FileLock":
        deadline = time.monotonic() + self.timeout
        self.path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.write(self.fd, f"{os.getpid()}\n".encode("ascii"))
                return self
            except FileExistsError:
                if self._remove_stale_lock():
                    continue
                if time.monotonic() >= deadline:
                    raise GitRepositoryError(
                        f"Timed out waiting for repository cache lock: {self.path}. "
                        "Another SCC process may still be synchronizing this source."
                    )
                time.sleep(0.1)

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        if self.fd is not None:
            os.close(self.fd)
        self.path.unlink(missing_ok=True)


class GitRepositoryService:
    """Synchronize named sources into a private shallow cache."""

    def __init__(
        self,
        cache_root: Optional[str | Path] = None,
        *,
        command_timeout: Optional[float] = None,
    ) -> None:
        root = cache_root or os.getenv("SCC_CACHE_DIR")
        if root:
            self.cache_root = Path(root).expanduser() / "repositories"
        else:
            xdg = os.getenv("XDG_CACHE_HOME")
            base = Path(xdg).expanduser() if xdg else Path.home() / ".cache"
            self.cache_root = base / "salt-config-cli" / "repositories"
        if command_timeout is None:
            try:
                command_timeout = float(os.getenv("SCC_GIT_TIMEOUT", "120"))
            except ValueError:
                command_timeout = 120.0
        self.command_timeout = max(5.0, command_timeout)

    @staticmethod
    def ensure_git_available() -> str:
        executable = shutil.which("git")
        if not executable:
            raise GitRepositoryError(
                "Git is not installed or is not on PATH. Install Git and retry; "
                "SCC does not bundle a separate GitHub client."
            )
        return executable

    @contextlib.contextmanager
    def _git_environment(self, name: str, source: RepositorySource) -> Iterator[dict[str, str]]:
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_CONFIG_NOSYSTEM"] = env.get("GIT_CONFIG_NOSYSTEM", "0")
        if not source.verify_tls:
            env["GIT_SSL_NO_VERIFY"] = "true"
        if source.auth == "ssh" and "GIT_SSH_COMMAND" not in env:
            env["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes"

        credential_labels = {
            "auto": "Git credential helper or SSH agent",
            "ssh": "SSH agent/key",
            "credential-helper": "Git credential helper",
        }
        if source.auth != "token":
            env["SCC_GIT_CREDENTIAL_SOURCE"] = credential_labels.get(source.auth, "Git")
            yield env
            return

        token, credential_source = get_source_token(name, kind=source.kind)
        if not token:
            raise GitRepositoryError(
                f"Source '{name}' uses token authentication but no token is available. "
                f"Run `scc repo login {name}` or set the source-specific SCC_GIT_TOKEN_* environment variable."
            )
        env["SCC_GIT_CREDENTIAL_SOURCE"] = credential_source
        if not source.url.startswith(("http://", "https://")):
            raise GitRepositoryError("Token authentication is supported only for HTTP(S) repository URLs")

        username = source.username or "x-access-token"
        with tempfile.TemporaryDirectory(prefix="scc-git-askpass-") as tmp:
            if os.name == "nt":
                askpass = Path(tmp) / "askpass.cmd"
                askpass.write_text(
                    "@echo off\r\n"
                    "echo %* | findstr /I username >nul\r\n"
                    "if %errorlevel%==0 (echo %SCC_GIT_USERNAME%) else (echo %SCC_GIT_PASSWORD%)\r\n",
                    encoding="utf-8",
                )
            else:
                askpass = Path(tmp) / "askpass.py"
                askpass.write_text(
                    f"#!{sys.executable}\n"
                    "import os, sys\n"
                    "prompt = ' '.join(sys.argv[1:]).lower()\n"
                    "value = os.environ.get('SCC_GIT_USERNAME', '') if 'username' in prompt else os.environ.get('SCC_GIT_PASSWORD', '')\n"
                    "print(value)\n",
                    encoding="utf-8",
                )
                askpass.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
            env["GIT_ASKPASS"] = str(askpass)
            env["SCC_GIT_USERNAME"] = username
            env["SCC_GIT_PASSWORD"] = token
            yield env

    def _run(
        self,
        git: str,
        args: Sequence[str],
        *,
        cwd: Optional[Path] = None,
        env: Optional[dict[str, str]] = None,
    ) -> CommandResult:
        try:
            completed = subprocess.run(
                [git, *args],
                cwd=str(cwd) if cwd else None,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=self.command_timeout,
            )
        except subprocess.TimeoutExpired as exc:
            operation = " ".join(args[:2])
            raise GitRepositoryError(
                f"git {operation} timed out after {self.command_timeout:g} seconds. "
                "Check network/VPN access, repository credentials, or SCC_GIT_TIMEOUT."
            ) from exc
        if completed.returncode != 0:
            stderr = completed.stderr.strip() or completed.stdout.strip() or "unknown Git error"
            secret = (env or {}).get("SCC_GIT_PASSWORD")
            if secret:
                stderr = stderr.replace(secret, "***")
            raise GitRepositoryError(f"git {' '.join(args[:2])} failed: {stderr}")
        return CommandResult(tuple(args), completed.stdout.strip(), completed.stderr.strip())

    def sync(self, name: str, source: RepositorySource, *, refresh: bool = True) -> SyncedRepository:
        git = self.ensure_git_available()
        cache_key = f"{name}-{source_fingerprint(source)}"
        repository_path = self.cache_root / cache_key
        lock_path = self.cache_root / f".{cache_key}.lock"
        self.cache_root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.cache_root, stat.S_IRWXU)
        except OSError:
            pass

        with _FileLock(lock_path), self._git_environment(name, source) as env:
            credential_source = env.get("SCC_GIT_CREDENTIAL_SOURCE", "none")
            if not (repository_path / ".git").exists():
                if repository_path.exists():
                    shutil.rmtree(repository_path)
                repository_path.mkdir(parents=True, exist_ok=True)
                self._run(git, ["init", "--quiet"], cwd=repository_path, env=env)
                self._run(git, ["remote", "add", "origin", source.url], cwd=repository_path, env=env)
            else:
                self._run(git, ["remote", "set-url", "origin", source.url], cwd=repository_path, env=env)

            if refresh or not (repository_path / ".git" / "FETCH_HEAD").exists():
                self._run(
                    git,
                    ["fetch", "--quiet", "--force", "--prune", "--depth", "1", "origin", source.ref],
                    cwd=repository_path,
                    env=env,
                )
                self._run(git, ["checkout", "--quiet", "--detach", "FETCH_HEAD"], cwd=repository_path, env=env)
                self._run(git, ["reset", "--quiet", "--hard", "HEAD"], cwd=repository_path, env=env)
                self._run(git, ["clean", "-ffdx", "--quiet"], cwd=repository_path, env=env)

            commit = self._run(git, ["rev-parse", "HEAD"], cwd=repository_path, env=env).stdout
            committed_at = self._run(git, ["show", "-s", "--format=%cI", "HEAD"], cwd=repository_path, env=env).stdout
            return SyncedRepository(
                name=name,
                source=source,
                path=repository_path,
                commit=commit,
                committed_at=committed_at,
                credential_source=credential_source,
            )

    def test(self, name: str, source: RepositorySource) -> SyncedRepository:
        """Validate access and resolve the configured ref without copying content."""
        return self.sync(name, source, refresh=True)


class ContentWorkspaceService:
    """Assemble immutable, reviewable state+data packages from Git sources."""

    def __init__(self, workspace_root: Optional[str | Path] = None) -> None:
        self.workspace_root = Path(workspace_root or ".scc/work").expanduser()

    @staticmethod
    def _safe_join(root: Path, relative: str) -> Path:
        if any(char in relative for char in ("\\", "\0", "\n", "\r")):
            raise GitRepositoryError(f"Repository path contains unsupported characters: {relative!r}")
        posix_path = PurePosixPath(relative)
        if posix_path.is_absolute() or any(part in {"", ".", ".."} for part in posix_path.parts):
            raise GitRepositoryError(f"Repository path must be a safe relative path: {relative}")
        candidate = (root / posix_path).resolve()
        resolved_root = root.resolve()
        try:
            candidate.relative_to(resolved_root)
        except ValueError as exc:
            raise GitRepositoryError(f"Repository path escapes the configured root: {relative}") from exc
        return candidate

    @staticmethod
    def _validate_resource(resource: str) -> str:
        cleaned = resource.strip().replace("\\", "/")
        path = PurePosixPath(cleaned)
        if (
            not cleaned
            or path.is_absolute()
            or any(part in {"", ".", ".."} for part in path.parts)
            or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in path.parts)
        ):
            raise GitRepositoryError(
                "resource must be a relative name using letters, numbers, '.', '_' or '-' "
                "(nested resources may use '/')"
            )
        return path.as_posix()

    @staticmethod
    def _validate_selector(value: str, *, name: str) -> str:
        cleaned = value.strip()
        if cleaned and not re.fullmatch(r"[A-Za-z0-9_.-]+", cleaned):
            raise GitRepositoryError(
                f"{name} must use only letters, numbers, '.', '_' or '-'"
            )
        return cleaned

    @staticmethod
    def _source_relative_path(source: RepositorySource, relative: str) -> str:
        if source.root in {"", "."}:
            return relative
        return str(PurePosixPath(source.root) / PurePosixPath(relative))

    @staticmethod
    def _validate_tree(path: Path) -> tuple[list[Path], list[str]]:
        files: list[Path] = []
        warnings: list[str] = []
        total = 0
        for item in sorted(path.rglob("*")):
            if item.is_symlink():
                raise GitRepositoryError(f"Symbolic links are not allowed in deployable content: {item}")
            if item.is_dir():
                if item.name == ".git":
                    raise GitRepositoryError(f"Nested Git metadata is not deployable content: {item}")
                continue
            if not item.is_file():
                continue
            size = item.stat().st_size
            if size > _MAX_FILE_SIZE:
                raise GitRepositoryError(f"File exceeds the 10 MiB safety limit: {item}")
            total += size
            if total > _MAX_PACKAGE_SIZE:
                raise GitRepositoryError("Content package exceeds the 100 MiB safety limit")
            try:
                text = item.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise GitRepositoryError(f"Deployable Salt content must be UTF-8 text: {item}") from exc
            if item.suffix.lower() in {".yaml", ".yml"}:
                try:
                    yaml.safe_load(text)
                except yaml.YAMLError as exc:
                    raise GitRepositoryError(f"Invalid YAML in {item}: {exc}") from exc
            files.append(item)

        if not any(item.suffix == ".sls" for item in files):
            raise GitRepositoryError(f"No .sls state file found under {path}")
        if not any(item.name == "map.jinja" for item in files):
            warnings.append("map.jinja was not found; this is valid only if the state does not use a mapping layer")
        if not any(item.name in {"defaults.yaml", "defaults.yml"} for item in files):
            warnings.append("defaults.yaml was not found; document the expected pillar/default contract")
        return files, warnings

    @staticmethod
    def _copy_tree(source: Path, destination: Path) -> None:
        if destination.exists():
            shutil.rmtree(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination, symlinks=False)

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def resolve_state_directory(self, repository: SyncedRepository, resource: str) -> Path:
        """Return the validated repository directory for one Salt resource."""
        return self._state_path(repository, resource)

    def resolve_data_file(
        self,
        repository: SyncedRepository,
        resource: str,
        *,
        environment: str = "",
        version: str = "",
        values: str = "",
        explicit_path: Optional[str] = None,
    ) -> Path:
        """Resolve and validate one customer values YAML file."""
        return self._data_path(
            repository,
            resource,
            environment=environment,
            version=version,
            values=values,
            explicit_path=explicit_path,
        )

    def _state_path(self, repository: SyncedRepository, resource: str) -> Path:
        resource = self._validate_resource(resource)
        layout = repository.source.layout or "{resource}"
        relative = layout.format(resource=resource, environment="", version="", values="")
        source_relative = self._source_relative_path(repository.source, relative)
        path = self._safe_join(repository.path, source_relative)
        if not path.is_dir():
            raise GitRepositoryError(
                f"State resource '{resource}' was not found at {source_relative} "
                f"in source '{repository.name}' ({repository.commit[:12]})"
            )
        return path

    def _data_path(
        self,
        repository: SyncedRepository,
        resource: str,
        *,
        environment: str,
        version: str,
        values: str,
        explicit_path: Optional[str],
    ) -> Path:
        resource = self._validate_resource(resource)
        environment = self._validate_selector(environment, name="environment")
        version = self._validate_selector(version, name="version")
        values = self._validate_selector(values, name="values")
        candidates: list[str] = []
        if explicit_path:
            candidates.append(explicit_path)
        elif repository.source.layout:
            layout = repository.source.layout
            required = {
                "environment": environment,
                "version": version,
                "values": values or environment,
            }
            missing = [name for name, selected in required.items() if f"{{{name}}}" in layout and not selected]
            if missing:
                flags = ", ".join(f"--{name}" for name in missing)
                raise GitRepositoryError(
                    f"Data source '{repository.name}' layout requires {flags}"
                )
            candidates.append(
                layout.format(
                    resource=resource,
                    environment=environment,
                    version=version,
                    values=values or environment,
                )
            )
        else:
            if values:
                candidates.append(f"{resource}/{values}/values.yaml")
                candidates.append(f"{resource}/{values}.yaml")
            if environment and version:
                candidates.append(f"{environment}/{version}/{resource}/values.yaml")
                candidates.append(f"{environment}/{version}/{resource}.yaml")
                candidates.append(f"{resource}/{version}/{environment}/values.yaml")
                candidates.append(f"{resource}/{version}/{environment}.yaml")
            if environment:
                candidates.append(f"{environment}/{resource}/values.yaml")
                candidates.append(f"{environment}/{resource}.yaml")
                candidates.append(f"{resource}/{environment}/values.yaml")
                candidates.append(f"{resource}/{environment}.yaml")
            candidates.append(f"{resource}/values.yaml")
            candidates.append(f"{resource}.yaml")

        checked: list[str] = []
        for relative in dict.fromkeys(candidates):
            source_relative = self._source_relative_path(repository.source, relative)
            checked.append(source_relative)
            path = self._safe_join(repository.path, source_relative)
            if path.is_file():
                if path.is_symlink():
                    raise GitRepositoryError(f"Symbolic links are not allowed for data files: {path}")
                if path.stat().st_size > _MAX_FILE_SIZE:
                    raise GitRepositoryError(f"Data file exceeds the 10 MiB safety limit: {path}")
                try:
                    data = yaml.safe_load(path.read_text(encoding="utf-8"))
                except (UnicodeDecodeError, yaml.YAMLError) as exc:
                    raise GitRepositoryError(f"Invalid UTF-8 YAML data file {path}: {exc}") from exc
                if not isinstance(data, dict):
                    raise GitRepositoryError(f"Data file must contain a YAML mapping: {path}")
                return path
        raise GitRepositoryError(
            "Customer data file was not found. Checked: " + ", ".join(checked)
        )

    def build(
        self,
        resource: str,
        states_repository: SyncedRepository,
        *,
        data_repository: Optional[SyncedRepository] = None,
        environment: str = "",
        version: str = "",
        values: str = "",
        data_path: Optional[str] = None,
        state_entrypoint: Optional[str] = None,
    ) -> ContentPackage:
        resource = self._validate_resource(resource)
        environment = self._validate_selector(environment, name="environment")
        version = self._validate_selector(version, name="version")
        values = self._validate_selector(values, name="values")

        state_source_path = self._state_path(states_repository, resource)
        state_files, warnings = self._validate_tree(state_source_path)

        self.workspace_root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.workspace_root, stat.S_IRWXU)
        except OSError:
            pass
        package_root = self._safe_join(self.workspace_root, resource)
        package_root.parent.mkdir(parents=True, exist_ok=True)
        staging_root = Path(
            tempfile.mkdtemp(prefix=f".{package_root.name}.staging-", dir=package_root.parent)
        )

        try:
            states_dir = staging_root / "states" / resource
            self._copy_tree(state_source_path, states_dir)

            copied_data: Optional[Path] = None
            data_source_path: Optional[Path] = None
            if data_repository:
                data_source_path = self._data_path(
                    data_repository,
                    resource,
                    environment=environment,
                    version=version,
                    values=values,
                    explicit_path=data_path,
                )
                copied_data = staging_root / "data" / data_source_path.name
                copied_data.parent.mkdir(parents=True, exist_ok=True)
                try:
                    os.chmod(copied_data.parent, stat.S_IRWXU)
                except OSError:
                    pass
                shutil.copy2(data_source_path, copied_data)
                try:
                    os.chmod(copied_data, stat.S_IRUSR | stat.S_IWUSR)
                except OSError:
                    pass

            if state_entrypoint:
                requested = state_entrypoint.strip().replace("\\", "/")
                requested_path = PurePosixPath(requested)
                if (
                    requested_path.is_absolute()
                    or ".." in requested_path.parts
                    or requested_path.suffix != ".sls"
                ):
                    raise GitRepositoryError("state entrypoint must be a safe relative .sls path")
                selected_entrypoint = states_dir / requested_path
                if not selected_entrypoint.is_file():
                    raise GitRepositoryError(
                        f"State entrypoint '{requested}' was not found under resource '{resource}'"
                    )
                entrypoint = str(PurePosixPath(resource) / requested_path)
            else:
                preferred = states_dir / f"{Path(resource).name}.sls"
                if preferred.exists():
                    entrypoint = str(PurePosixPath(resource) / preferred.name)
                else:
                    first_sls = sorted(states_dir.rglob("*.sls"))[0]
                    entrypoint = str(PurePosixPath(resource) / first_sls.relative_to(states_dir).as_posix())

            content_files: list[ContentFile] = []
            for source_file in state_files:
                copied = states_dir / source_file.relative_to(state_source_path)
                content_files.append(
                    ContentFile(
                        file_type="state",
                        path=copied.relative_to(staging_root).as_posix(),
                        sha256=self._hash_file(copied),
                        size=copied.stat().st_size,
                    )
                )
            if copied_data:
                content_files.append(
                    ContentFile(
                        file_type="data",
                        path=copied_data.relative_to(staging_root).as_posix(),
                        sha256=self._hash_file(copied_data),
                        size=copied_data.stat().st_size,
                    )
                )

            if package_root.exists():
                shutil.rmtree(package_root)
            os.replace(staging_root, package_root)

            final_states_dir = package_root / "states" / resource
            final_data_file = package_root / "data" / copied_data.name if copied_data else None
            repository_data_path = (
                data_source_path.relative_to(data_repository.path).as_posix()
                if data_repository and data_source_path
                else None
            )
            return ContentPackage(
                resource=resource,
                workspace=package_root,
                states_dir=final_states_dir,
                state_entrypoint=entrypoint,
                states_source=states_repository,
                states_repository_path=state_source_path.relative_to(states_repository.path).as_posix(),
                environment=environment,
                version=version,
                values=values,
                data_file=final_data_file,
                data_source=data_repository,
                data_repository_path=repository_data_path,
                files=tuple(content_files),
                warnings=tuple(warnings),
            )
        except Exception:
            shutil.rmtree(staging_root, ignore_errors=True)
            raise

