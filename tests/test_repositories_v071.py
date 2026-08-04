from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from salt_config_cli.cli.main import cli
from salt_config_cli.cli.workflow_cmds import _package_summary
from salt_config_cli.core.repositories import RepositorySource, RepositoryStore
from salt_config_cli.services.git_repository import ContentWorkspaceService, GitRepositoryService


def _git_repo(path: Path, files: dict[str, str]) -> Path:
    if not shutil.which("git"):
        pytest.skip("git executable is required")
    for relative, text in files.items():
        target = path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "SCC Tests"], check=True)
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "initial"], check=True)
    return path


@pytest.fixture()
def repositories(tmp_path: Path) -> tuple[Path, Path]:
    states = _git_repo(
        tmp_path / "states-repo",
        {
            "vcf-infra/dns/dns.sls": "dns-ready:\n  test.nop:\n    - name: ready\n",
            "vcf-infra/dns/map.jinja": "{% set dns = salt['pillar.get']('dns', {}) %}\n",
            "vcf-infra/dns/defaults.yaml": "dns:\n  servers: []\n",
            "vcf-infra/dns/files/resolv.conf.jinja": "nameserver {{ dns.servers[0] }}\n",
        },
    )
    data = _git_repo(
        tmp_path / "data-repo",
        {"prod/9.1.1/dns.yaml": "dns:\n  servers:\n    - 10.0.0.10\n"},
    )
    return states, data


def test_repository_store_is_separate_and_migrates_legacy(tmp_path: Path) -> None:
    connection = tmp_path / ".scc" / "config.yaml"
    connection.parent.mkdir(parents=True)
    connection.write_text(
        yaml.safe_dump(
            {
                "server_url": "https://raas.example.test",
                "username": "root",
                "git_repo_url": "https://example.test/org/vcf-salt.git",
                "git_branch": "release/9.1.1",
                "git_resources_path": "vcf-infra",
                "git_data_repo_url": "git@example.test:org/customer-data.git",
                "git_data_branch": "approved",
                "git_data_resources_path": "environments",
            }
        ),
        encoding="utf-8",
    )

    store = RepositoryStore(connection_config=connection)
    document = store.load()

    assert store.path == connection.parent / "repositories.yaml"
    assert store.last_migration
    assert document.default_states_source == "vcf-salt"
    assert document.sources["vcf-salt"].ref == "release/9.1.1"
    assert document.default_data_source == "customer-data"
    assert document.sources["customer-data"].layout == "{resource}/{values}.yaml"
    assert store.path.exists()
    assert "server_url" not in store.path.read_text(encoding="utf-8")


def test_git_sync_and_local_package_metadata(repositories: tuple[Path, Path], tmp_path: Path) -> None:
    states_path, data_path = repositories
    git_service = GitRepositoryService(tmp_path / "cache")
    states = git_service.sync(
        "vcf-salt",
        RepositorySource(kind="states", url=str(states_path), ref="main", root="vcf-infra", layout="{resource}"),
    )
    data = git_service.sync(
        "customer-data",
        RepositorySource(
            kind="data",
            url=str(data_path),
            ref="main",
            root=".",
            layout="{environment}/{version}/{resource}.yaml",
        ),
    )

    package = ContentWorkspaceService(tmp_path / "work").build(
        "dns",
        states,
        data_repository=data,
        environment="prod",
        version="9.1.1",
    )

    summary = _package_summary(package)
    assert package.state_entrypoint == "dns/dns.sls"
    assert (package.states_dir / "files" / "resolv.conf.jinja").exists()
    assert package.data_file and package.data_file.exists()
    assert package.data_repository_path == "prod/9.1.1/dns.yaml"
    assert summary["states"]["commit"] == states.commit
    assert summary["data"]["commit"] == data.commit
    assert {item.file_type for item in package.files} == {"state", "data"}
    assert all(len(item.sha256) == 64 for item in package.files)
    assert not (package.workspace / "release.yaml").exists()



def test_package_summary_is_json_serializable_without_manifest(
    repositories: tuple[Path, Path], tmp_path: Path
) -> None:
    states_path, data_path = repositories
    service = GitRepositoryService(tmp_path / "cache")
    package = ContentWorkspaceService(tmp_path / "work").build(
        "dns",
        service.sync(
            "vcf-salt",
            RepositorySource(
                kind="states",
                url=str(states_path),
                ref="main",
                root="vcf-infra",
                layout="{resource}",
            ),
        ),
        data_repository=service.sync(
            "customer-data",
            RepositorySource(
                kind="data",
                url=str(data_path),
                ref="main",
                layout="{environment}/{version}/{resource}.yaml",
            ),
        ),
        environment="prod",
        version="9.1.1",
    )
    summary = _package_summary(package)
    rendered = json.dumps(summary)
    assert package.states_source.commit in rendered
    assert package.data_source and package.data_source.commit in rendered
    assert "manifest" not in summary
    assert not any(path.name == "release.yaml" for path in package.workspace.rglob("*"))

def test_cli_repo_catalog_and_deploy_plan(
    repositories: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    states_path, data_path = repositories
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "--theme",
            "plain",
            "repo",
            "add",
            "vcf-salt",
            "--kind",
            "states",
            "--url",
            str(states_path),
            "--root",
            "vcf-infra",
            "--layout",
            "{resource}",
            "--default",
        ],
    )
    assert result.exit_code == 0, result.output

    result = runner.invoke(
        cli,
        [
            "--theme",
            "plain",
            "repo",
            "add",
            "customer-data",
            "--kind",
            "data",
            "--url",
            str(data_path),
            "--layout",
            "{environment}/{version}/{resource}.yaml",
            "--default",
        ],
    )
    assert result.exit_code == 0, result.output

    result = runner.invoke(cli, ["--theme", "plain", "repo", "list", "--json"])
    assert result.exit_code == 0, result.output
    catalog = json.loads(result.output)
    assert catalog["default_states_source"] == "vcf-salt"
    assert catalog["default_data_source"] == "customer-data"

    work = tmp_path / "review-work"
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            cli,
            [
                "--theme",
                "plain",
                "deploy",
                "dns",
                "--environment",
                "prod",
                "--version",
                "9.1.1",
                "--work-dir",
                str(work),
            ],
        )
    assert result.exit_code == 0, result.output
    assert "No RaaS changes have been made" in result.output
    assert "PLAN ONLY" in result.output
    assert "State commit" in result.output
    assert (work / "dns" / "states" / "dns" / "dns.sls").exists()
    assert not (work / "dns" / "release.yaml").exists()


def test_pull_copies_complete_resource_tree(
    repositories: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    states_path, _ = repositories
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    runner = CliRunner()

    add = runner.invoke(
        cli,
        [
            "--theme",
            "plain",
            "repo",
            "add",
            "vcf-salt",
            "--kind",
            "states",
            "--url",
            str(states_path),
            "--root",
            "vcf-infra",
            "--layout",
            "{resource}",
            "--default",
        ],
    )
    assert add.exit_code == 0, add.output

    destination = tmp_path / "downloaded"
    result = runner.invoke(
        cli,
        ["--theme", "plain", "pull", "dns", "--dir", str(destination)],
    )
    assert result.exit_code == 0, result.output
    assert (destination / "dns" / "dns.sls").exists()
    assert (destination / "dns" / "files" / "resolv.conf.jinja").exists()



def test_repository_url_rejects_option_injection() -> None:
    with pytest.raises(ValueError, match="must not begin"):
        RepositorySource(kind="states", url="--upload-pack=evil", ref="main")


def test_approved_manifest_option_is_removed() -> None:
    help_result = CliRunner().invoke(cli, ["--theme", "plain", "deploy", "--help"])
    assert help_result.exit_code == 0, help_result.output
    assert "approved-manifest" not in help_result.output

    rejected = CliRunner().invoke(
        cli,
        [
            "--theme",
            "plain",
            "deploy",
            "dns",
            "--approved-manifest",
            "release.yaml",
        ],
    )
    assert rejected.exit_code != 0
    assert "No such option" in rejected.output


def test_refreshed_git_commit_is_displayed_without_an_approval_artifact(
    repositories: tuple[Path, Path], tmp_path: Path
) -> None:
    states_path, data_path = repositories
    service = GitRepositoryService(tmp_path / "cache")
    state_source = RepositorySource(
        kind="states", url=str(states_path), ref="main", root="vcf-infra", layout="{resource}"
    )
    data_source = RepositorySource(
        kind="data",
        url=str(data_path),
        ref="main",
        root=".",
        layout="{environment}/{version}/{resource}.yaml",
    )
    first = ContentWorkspaceService(tmp_path / "review").build(
        "dns",
        service.sync("vcf-salt", state_source),
        data_repository=service.sync("customer-data", data_source),
        environment="prod",
        version="9.1.1",
    )
    first_commit = _package_summary(first)["states"]["commit"]

    state_file = states_path / "vcf-infra/dns/dns.sls"
    state_file.write_text("changed:\n  test.nop:\n    - name: changed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(states_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(states_path), "commit", "-qm", "changed"], check=True)

    second = ContentWorkspaceService(tmp_path / "review").build(
        "dns",
        service.sync("vcf-salt", state_source, refresh=True),
        data_repository=service.sync("customer-data", data_source, refresh=True),
        environment="prod",
        version="9.1.1",
    )
    second_summary = _package_summary(second)
    assert second_summary["states"]["commit"] != first_commit
    assert not (second.workspace / "release.yaml").exists()


def test_repo_import_merges_non_secret_catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    source_file = tmp_path / "repositories.yaml"
    source_file.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "default_states_source": "vcf-salt",
                "sources": {
                    "vcf-salt": {
                        "kind": "states",
                        "url": str(tmp_path / "repo"),
                        "ref": "main",
                        "root": "vcf-infra",
                        "layout": "{resource}",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    result = CliRunner().invoke(cli, ["--theme", "plain", "repo", "import", str(source_file)])
    assert result.exit_code == 0, result.output
    catalog = RepositoryStore().load()
    assert catalog.default_states_source == "vcf-salt"
    assert "vcf-salt" in catalog.sources


def test_repeated_plan_replaces_workspace_without_stale_data(
    repositories: tuple[Path, Path], tmp_path: Path
) -> None:
    states_path, data_path = repositories
    service = GitRepositoryService(tmp_path / "cache")
    states = service.sync(
        "vcf-salt",
        RepositorySource(kind="states", url=str(states_path), ref="main", root="vcf-infra", layout="{resource}"),
    )
    data = service.sync(
        "customer-data",
        RepositorySource(
            kind="data",
            url=str(data_path),
            ref="main",
            root=".",
            layout="{environment}/{version}/{resource}.yaml",
        ),
    )
    workspace = ContentWorkspaceService(tmp_path / "work")
    first = workspace.build(
        "dns",
        states,
        data_repository=data,
        environment="prod",
        version="9.1.1",
    )
    assert first.data_file and first.data_file.exists()

    second = workspace.build("dns", states)
    assert second.data_file is None
    assert second.data_source is None
    assert second.data_repository_path is None
    assert {item.file_type for item in second.files} == {"state"}
    assert not (second.workspace / "data").exists()
    assert not (second.workspace / "release.yaml").exists()
    assert not list(second.workspace.parent.glob(".dns.staging-*"))


def test_data_layout_reports_missing_required_selectors(
    repositories: tuple[Path, Path], tmp_path: Path
) -> None:
    _, data_path = repositories
    data = GitRepositoryService(tmp_path / "cache").sync(
        "customer-data",
        RepositorySource(
            kind="data",
            url=str(data_path),
            ref="main",
            layout="{environment}/{version}/{resource}.yaml",
        ),
    )
    with pytest.raises(Exception, match=r"requires --environment, --version"):
        ContentWorkspaceService(tmp_path / "work").resolve_data_file(data, "dns")


def test_resource_selector_rejects_unsafe_names(
    repositories: tuple[Path, Path], tmp_path: Path
) -> None:
    states_path, _ = repositories
    states = GitRepositoryService(tmp_path / "cache").sync(
        "vcf-salt",
        RepositorySource(kind="states", url=str(states_path), ref="main", root="vcf-infra"),
    )
    with pytest.raises(Exception, match="resource must be a relative name"):
        ContentWorkspaceService(tmp_path / "work").build("../dns", states)


def test_apply_can_be_cancelled_before_any_raas_change(
    repositories: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    states_path, data_path = repositories
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    runner = CliRunner()

    for args in (
        [
            "repo", "add", "vcf-salt", "--kind", "states", "--url", str(states_path),
            "--root", "vcf-infra", "--layout", "{resource}", "--default",
        ],
        [
            "repo", "add", "customer-data", "--kind", "data", "--url", str(data_path),
            "--layout", "{environment}/{version}/{resource}.yaml", "--default",
        ],
    ):
        result = runner.invoke(cli, ["--theme", "plain", *args])
        assert result.exit_code == 0, result.output

    work = tmp_path / "work"
    apply_result = runner.invoke(
        cli,
        [
            "--theme", "plain", "deploy", "dns", "--environment", "prod", "--version", "9.1.1",
            "--mode", "apply", "--target-group", "vcf-prod", "--work-dir", str(work),
        ],
    )
    assert apply_result.exit_code == 0, apply_result.output
    assert "cancelled before any RaaS files" in apply_result.output
    assert "Connected to" not in apply_result.output


def test_repository_store_save_is_atomic_and_owner_only(tmp_path: Path) -> None:
    store = RepositoryStore(tmp_path / "repositories.yaml", connection_config=tmp_path / "config.yaml")
    store.add(
        "vcf-salt",
        RepositorySource(kind="states", url=str(tmp_path / "states"), ref="main"),
        make_default=True,
    )
    assert store.path.exists()
    assert not list(tmp_path.glob(".repositories.yaml.*.tmp"))
    if os.name != "nt":
        assert store.path.stat().st_mode & 0o077 == 0


def test_repository_url_rejects_embedded_or_query_credentials() -> None:
    with pytest.raises(ValueError, match="embedded credentials"):
        RepositorySource(kind="states", url="ssh://user:secret@git.example.test/org/repo.git")
    with pytest.raises(ValueError, match="query parameters"):
        RepositorySource(kind="states", url="https://git.example.test/org/repo.git?token=secret")


def test_token_auth_fails_early_without_a_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SCC_GIT_TOKEN_PRIVATE", raising=False)
    monkeypatch.delenv("SCC_GIT_TOKEN", raising=False)
    monkeypatch.delenv("SCC_GIT_DATA_TOKEN", raising=False)
    source = RepositorySource(
        kind="states",
        url="https://git.example.test/org/private.git",
        ref="main",
        auth="token",
    )
    with pytest.raises(Exception, match="no token is available"):
        GitRepositoryService(tmp_path / "cache").sync("private", source)
