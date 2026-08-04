from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from salt_config_cli import __version__
from salt_config_cli.cli.main import cli


def invoke_plain(*args: str):
    return CliRunner().invoke(cli, ["--theme", "plain", *args])


def test_version_bumped_for_customer_journey_release() -> None:
    assert __version__ == "0.8.2"


def test_tutorial_list_exposes_customer_journeys() -> None:
    result = invoke_plain("tutorial", "list")
    assert result.exit_code == 0, result.output
    assert "dns" in result.output
    assert "kb-search" in result.output
    assert "Add the saltext-vcf and customer-values repositories" in result.output
    assert "Search the static saltext-vcf catalog" in result.output


def test_dns_tutorial_is_concrete_simple_and_network_free() -> None:
    result = invoke_plain("tutorial", "dns", "--non-interactive")
    assert result.exit_code == 0, result.output
    output = result.output
    normalized = " ".join(output.split())
    assert "No network calls are made by this tutorial" in output
    assert "scc repo add vcf-salt" in output
    assert "--root vcf-infra" in output
    assert "--layout '{resource}'" in output
    assert "scc repo add customer-values" in output
    assert "{environment}/{version}/{resource}/values.yaml" in output
    assert "scc repo test --all" in output
    assert "scc deploy dns --environment prod --version 9.1.1" in output
    assert "--mode dry-run" in output
    assert "--mode apply" in output
    assert "Customer values are never uploaded to the RaaS file server" in normalized
    assert "No persistent saved job is created" in normalized


def test_kb_search_tutorial_uses_static_catalog_and_direct_execution() -> None:
    result = invoke_plain("tutorial", "kb-search", "--non-interactive")
    assert result.exit_code == 0, result.output
    output = result.output
    normalized = " ".join(output.split())
    assert "solutions/catalog.yaml" in output
    assert "static and Git-reviewed" in normalized
    assert "never invent a KB-to-SLS mapping" in normalized
    assert "scc kb search 'DNS lookup failed'" in output
    assert "scc kb show KB-123456" in output
    assert "scc kb plan KB-123456" in output
    assert "scc kb execute KB-123456" in output
    assert "--mode dry-run" in output
    assert "--mode apply" in output
    assert "runtime pillar" in output
    assert "RaaS JID" in output


def test_customer_journey_tutorials_avoid_rejected_complexity() -> None:
    runner = CliRunner()
    for topic in ("dns", "kb-search", "kb"):
        result = runner.invoke(cli, ["--theme", "plain", "tutorial", topic, "--non-interactive"])
        assert result.exit_code == 0, result.output
        lowered = result.output.lower()
        assert "approved-manifest" not in lowered
        assert "release.yaml" not in lowered
        assert "pillar.yaml" not in lowered
        assert "validate.sls" not in lowered
        assert "configure.sls" not in lowered


def test_customer_journey_tutorials_render_with_rich_theme() -> None:
    runner = CliRunner()
    for topic in ("dns", "kb-search"):
        result = runner.invoke(cli, ["--theme", "enterprise", "tutorial", topic, "--non-interactive"])
        assert result.exit_code == 0, result.output
        assert "No network calls are made by this tutorial" in result.output
        assert "You are ready" in result.output


def test_general_tutorial_points_to_concrete_journeys() -> None:
    result = invoke_plain("tutorial", "--non-interactive")
    assert result.exit_code == 0, result.output
    assert "scc tutorial dns" in result.output
    assert "scc tutorial kb-search" in result.output


def test_customer_journeys_document_is_packaged_in_source_tree() -> None:
    root = Path(__file__).resolve().parents[1]
    document = root / "docs" / "CUSTOMER_JOURNEYS.md"
    assert document.is_file()
    text = document.read_text(encoding="utf-8")
    assert "Customer Journeys" in text
    assert "scc tutorial dns" in text
    assert "scc tutorial kb-search" in text
