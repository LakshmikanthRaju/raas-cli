from __future__ import annotations

import importlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from salt_config_cli.cli.main import cli
from salt_config_cli.core.kb_catalog import CatalogIndex, KBCatalogService
from salt_config_cli.core.repositories import RepositorySource
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
def kb_repositories(tmp_path: Path) -> tuple[Path, Path]:
    catalog = """\
api_version: saltext.vcf/catalog/v1
kind: KBSolutionCatalog
catalog_version: 1.1.0
solutions:
  - solution_id: kb-dns-001
    kb_id: KB-DNS-001
    title: DNS mismatch
    components: [NSX Manager]
    versions: [9.1.x]
    symptoms: [DNS lookup failed]
    status: verified
    risk: medium
    solution_path: kb-dns/solution.yaml
    state: vcf-infra.dns.dns
"""
    solution = """\
api_version: saltext.vcf/v1
kind: KBResolution
metadata:
  id: kb-dns-001
  title: DNS mismatch
  description: Correct approved DNS values using the existing DNS state.
  status: verified
  maturity: production
kb:
  provider: broadcom
  id: KB-DNS-001
applicability:
  products: [VCF]
  components: [NSX Manager]
  versions: [9.1.x]
  symptoms: [DNS lookup failed]
  error_patterns: [unable to resolve host]
execution:
  state: vcf-infra.dns.dns
  description: Apply approved DNS configuration.
  values_schema: solutions/schemas/dns-values.schema.yaml
  dry_run_supported: true
risk:
  level: medium
  requires_confirmation: true
"""
    states = _git_repo(
        tmp_path / "saltext-vcf",
        {
            "solutions/catalog.yaml": catalog,
            "solutions/kb-dns/solution.yaml": solution,
            "solutions/schemas/dns-values.schema.yaml": "resource: dns\n",
            "vcf-infra/dns/dns.sls": "dns-configure:\n  test.nop:\n    - name: configure\n",
            "vcf-infra/dns/map.jinja": "{% set dns = salt['pillar.get']('dns', {}) %}\n",
            "vcf-infra/dns/default.yaml": "dns:\n  servers: []\n",
        },
    )
    values = _git_repo(
        tmp_path / "customer-values",
        {"prod/9.1.1/dns/values.yaml": "dns:\n  servers: [10.0.0.10]\n"},
    )
    return states, values


def _configure_sources(runner: CliRunner, states: Path, values: Path) -> None:
    for args in (
        [
            "repo", "add", "vcf-salt", "--kind", "states", "--url", str(states),
            "--root", "vcf-infra", "--layout", "{resource}", "--default",
        ],
        [
            "repo", "add", "customer-values", "--kind", "data", "--url", str(values),
            "--layout", "{environment}/{version}/{resource}/values.yaml", "--default",
        ],
    ):
        result = runner.invoke(cli, ["--theme", "plain", *args])
        assert result.exit_code == 0, result.output


def test_bundled_dns_ntp_demo_is_valid_searchable_and_simple() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--theme", "plain", "kb", "validate", "--demo", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["valid"] is True
    assert payload["solutions"] == 2

    result = runner.invoke(cli, ["--theme", "plain", "kb", "search", "clock skew", "--demo", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["matches"][0]["solution"]["kb"]["id"] == "DEMO-NTP-001"
    execution = payload["matches"][0]["solution"]["execution"]
    assert execution["state"] == "vcf-infra.ntp.ntp"
    assert execution["resolved_resource"] == "ntp"
    assert execution["resolved_entrypoint"] == "ntp.sls"
    assert "prechecks" not in execution
    assert "postchecks" not in execution
    assert "remediation" not in execution


def test_catalog_is_static_and_version_filtered() -> None:
    demo_root = Path(importlib.import_module("salt_config_cli.cli.kb_cmds").__file__).resolve().parent.parent / "data" / "kb_demo"
    service = KBCatalogService()
    catalog = service.load(service.discover(demo_root), repository_root=demo_root)
    solution = service.get(catalog, "DEMO-DNS-001")
    assert solution.execution.state == "vcf-infra.dns.dns"
    assert solution.execution.resolved_resource == "dns"
    assert solution.execution.resolved_entrypoint == "dns.sls"
    assert service.version_matches("9.1.1", ["9.1.x"])
    assert not service.version_matches("9.2.0", ["9.1.x"])
    assert service.search(catalog, "DNS disconnected")[0].solution.kb.id == "DEMO-DNS-001"


def test_legacy_single_remediation_index_is_read_compatible() -> None:
    index = CatalogIndex.model_validate({
        "solutions": [{
            "solution_id": "kb-one",
            "kb_id": "KB-ONE",
            "title": "One",
            "solution_path": "kb-one/solution.yaml",
            "remediation_states": ["vcf-infra.dns.dns"],
        }]
    })
    assert index.solutions[0].state == "vcf-infra.dns.dns"


def test_default_entrypoint_selects_conventional_resource_sls(
    kb_repositories: tuple[Path, Path], tmp_path: Path
) -> None:
    states_path, _ = kb_repositories
    service = GitRepositoryService(tmp_path / "cache")
    states = service.sync(
        "vcf-salt",
        RepositorySource(kind="states", url=str(states_path), ref="main", root="vcf-infra", layout="{resource}"),
    )
    package = ContentWorkspaceService(tmp_path / "work").build("dns", states, state_entrypoint="dns.sls")
    assert package.state_entrypoint == "dns/dns.sls"


def test_cli_reads_simple_mapping_from_states_repository(
    kb_repositories: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    states, values = kb_repositories
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    runner = CliRunner()
    _configure_sources(runner, states, values)

    result = runner.invoke(cli, ["--theme", "plain", "kb", "show", "KB-DNS-001", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["solution"]["metadata"]["status"] == "verified"
    assert payload["solution"]["execution"]["state"] == "vcf-infra.dns.dns"
    assert payload["solution"]["execution"]["resolved_entrypoint"] == "dns.sls"

    result = runner.invoke(cli, ["--theme", "plain", "kb", "validate", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["valid"] is True


def test_kb_execute_runs_one_direct_state_with_runtime_values(
    kb_repositories: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    states, values = kb_repositories
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("SCC_THEME", "plain")
    runner = CliRunner()
    _configure_sources(runner, states, values)

    main_module = importlib.import_module("salt_config_cli.cli.main")
    calls: list[tuple[str, dict]] = []
    monkeypatch.setattr(main_module.upload_file, "callback", lambda **kwargs: calls.append(("upload", kwargs)))
    monkeypatch.setattr(main_module.run_state, "callback", lambda **kwargs: calls.append(("run", kwargs)))
    monkeypatch.setattr(main_module.job_create, "callback", lambda **kwargs: calls.append(("job", kwargs)))
    monkeypatch.setattr(main_module.upload_pillar, "callback", lambda **kwargs: calls.append(("pillar", kwargs)))

    result = runner.invoke(
        cli,
        [
            "kb", "execute", "KB-DNS-001",
            "--environment", "prod",
            "--version", "9.1.1",
            "--component", "NSX Manager",
            "--target-group", "prod-nsx",
            "--mode", "dry-run",
            "--work-dir", str(tmp_path / "work"),
            "--no-show-tree",
        ],
    )
    assert result.exit_code == 0, result.output
    assert [name for name, _ in calls] == ["upload", "run"]
    run_call = [kwargs for name, kwargs in calls if name == "run"][0]
    assert Path(run_call["state_file"]).name == "dns.sls"
    assert run_call["test"] is True
    assert run_call["pillar_file"].endswith("/data/values.yaml")
    assert not any(name in {"job", "pillar"} for name, _ in calls)


def test_demo_state_folders_use_original_three_file_pattern() -> None:
    demo_root = Path(importlib.import_module("salt_config_cli.cli.kb_cmds").__file__).resolve().parent.parent / "data" / "kb_demo"
    for resource in ("dns", "ntp"):
        files = sorted(item.name for item in (demo_root / "vcf-infra" / resource).iterdir() if item.is_file())
        assert files == sorted(["default.yaml", f"{resource}.sls", "map.jinja"])


def test_kb_schema_is_simple_and_excludes_workflow_arrays(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--theme", "plain", "kb", "schema", "--kind", "solution"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    execution = payload["$defs"]["ExecutionMapping"]["properties"]
    assert "state" in execution
    assert "prechecks" not in execution
    assert "remediation" not in execution
    assert "postchecks" not in execution

    output = tmp_path / "catalog.schema.json"
    result = runner.invoke(cli, ["--theme", "plain", "kb", "schema", "--kind", "catalog", "--output", str(output)])
    assert result.exit_code == 0, result.output
    assert json.loads(output.read_text(encoding="utf-8"))["title"] == "CatalogIndex"


def test_kb_help_and_tutorial_are_available_and_simple() -> None:
    runner = CliRunner()
    for args in (["--theme", "plain", "kb", "--help"], ["--theme", "plain", "tutorial", "kb", "--non-interactive"]):
        result = runner.invoke(cli, args)
        assert result.exit_code == 0, result.output
    help_result = runner.invoke(cli, ["--theme", "plain", "kb", "execute", "--help"])
    assert help_result.exit_code == 0
    assert "--target-group" in help_result.output
    assert "--include-checks" not in help_result.output
    assert "--remediation-only" not in help_result.output
    assert "--approved-manifest" not in help_result.output
