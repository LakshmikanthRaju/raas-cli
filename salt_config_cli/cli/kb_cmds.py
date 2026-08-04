"""Static KB solution-catalog commands.

The Config AI Agent and human users search the same read-only catalog. The
catalog is maintained in Git beside saltext-vcf states; SCC never invents or
writes KB-to-SLS mappings at runtime.
"""

from __future__ import annotations

import contextlib
import json
import shutil
from pathlib import Path
from typing import Optional

import click

from salt_config_cli.cli.workflow_cmds import deploy_command
from salt_config_cli.core.kb_catalog import (
    CatalogIndex,
    KBCatalogError,
    KBCatalogService,
    KBSolution,
    LoadedCatalog,
    ExecutionMapping,
)
from salt_config_cli.core.repositories import RepositoryStore
from salt_config_cli.services.git_repository import GitRepositoryError, GitRepositoryService
from salt_config_cli.ui import (
    RichGroup,
    command_header,
    confirm_destructive,
    data_table,
    empty_state,
    kv_table,
    next_steps,
    result_summary,
    spinner,
    warn as ui_warn,
)


def _root_config_path(ctx: click.Context) -> Optional[str]:
    root = ctx.find_root()
    return (root.obj or {}).get("config_path") if root.obj else None


def _demo_root() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "kb_demo"


def _catalog_payload(catalog: LoadedCatalog) -> dict:
    return {
        "catalog_version": catalog.version,
        "catalog_path": str(catalog.path),
        "solutions": [_solution_payload(item) for item in catalog.solutions],
    }


def _solution_payload(solution: KBSolution) -> dict:
    payload = solution.model_dump(mode="json", exclude_none=True)
    payload["execution"]["resolved_resource"] = solution.execution.resolved_resource
    payload["execution"]["resolved_entrypoint"] = solution.execution.resolved_entrypoint
    return payload


def _load_catalog(
    ctx: click.Context,
    *,
    states_source: Optional[str],
    catalog_path: Optional[str],
    catalog_file: Optional[str],
    repository_file: Optional[str],
    refresh: bool,
    demo: bool,
    quiet: bool = False,
) -> tuple[LoadedCatalog, dict[str, str]]:
    service = KBCatalogService()
    if demo:
        root = _demo_root()
        path = service.discover(root, "solutions/catalog.yaml")
        return service.load(path, repository_root=root), {
            "source": "built-in demonstration",
            "ref": "package",
            "commit": "not applicable",
        }
    if catalog_file:
        path = Path(catalog_file).expanduser().resolve()
        repository_root = path.parent
        # If the file is under solutions/, state paths normally live one level up.
        if path.parent.name == "solutions":
            repository_root = path.parent.parent
        return service.load(path, repository_root=repository_root), {
            "source": "local catalog",
            "ref": "local",
            "commit": "not applicable",
        }

    store = RepositoryStore(repository_file, connection_config=_root_config_path(ctx))
    try:
        source_name, source = store.get(states_source, kind="states")
    except ValueError as exc:
        raise click.ClickException(f"{exc}. Configure the reusable-state repository with `scc repo setup`.") from exc
    try:
        progress = contextlib.nullcontext() if quiet else spinner(f"Syncing KB catalog from {source_name}@{source.ref}…")
        with progress:
            repository = GitRepositoryService().sync(source_name, source, refresh=refresh)
        path = service.discover(repository.path, catalog_path)
        catalog = service.load(path, repository_root=repository.path)
        return catalog, {
            "source": source_name,
            "ref": source.ref,
            "commit": repository.commit,
        }
    except (GitRepositoryError, KBCatalogError) as exc:
        raise click.ClickException(str(exc)) from exc


def _catalog_options(function):  # type: ignore[no-untyped-def]
    options = [
        click.option("--states-source", help="Named reusable-state source containing the static solutions catalog."),
        click.option("--catalog-path", help="Catalog path relative to the reusable-state repository."),
        click.option("--catalog-file", type=click.Path(exists=True, dir_okay=True), help="Read a local catalog file/directory instead of Git."),
        click.option("--repository-file", type=click.Path(exists=False), help="Use another repositories.yaml file."),
        click.option("--refresh/--no-refresh", default=True, show_default=True, help="Refresh the configured Git ref before loading the catalog."),
        click.option("--demo", is_flag=True, help="Use the bundled fictional DNS/NTP catalog examples."),
    ]
    for option in reversed(options):
        function = option(function)
    return function


def _solution_rows(solutions: list[KBSolution]) -> list[list[str]]:
    return [
        [
            item.kb.id,
            item.metadata.title,
            ", ".join(item.applicability.components) or "-",
            ", ".join(item.applicability.versions) or "all",
            item.metadata.status,
            item.risk.level,
        ]
        for item in solutions
    ]


def _render_solution(solution: KBSolution, provenance: dict[str, str]) -> None:
    command_header(
        "kb show",
        solution.metadata.title,
        description=solution.metadata.description or "Static KB-to-Salt solution mapping.",
        icon="doc",
        meta=[
            ("KB", f"{solution.kb.provider} {solution.kb.id}"),
            ("Status", solution.metadata.status),
            ("Catalog source", provenance.get("source", "-")),
            ("Commit", provenance.get("commit", "-")[:12]),
        ],
        mode=("READ ONLY", "black on #7dd3fc"),
    )
    kv_table(
        "Applicability",
        [
            ("Solution ID", solution.metadata.id),
            ("Components", ", ".join(solution.applicability.components) or "not restricted"),
            ("Versions", ", ".join(solution.applicability.versions) or "not restricted"),
            ("Symptoms", "; ".join(solution.applicability.symptoms) or "not listed"),
            ("Risk", solution.risk.level),
            ("Dry-run supported", "yes" if solution.execution.dry_run_supported else "no"),
            ("Values schema", solution.execution.values_schema or "not declared"),
        ],
    )
    execution = solution.execution
    data_table(
        "Mapped Salt state",
        [
            ("Resource", "scc.strong"),
            ("Static state mapping", "scc.cmd"),
            ("SLS", "scc.accent"),
            ("Purpose", "scc.value"),
        ],
        [[
            execution.resolved_resource,
            execution.state,
            execution.resolved_entrypoint,
            execution.description or "Apply the KB resolution using the reusable resource state.",
        ]],
        icon="gear",
        caption="One KB maps to one existing resource SLS. SCC and the AI agent never generate this mapping.",
    )


def _require_executable_catalog(catalog: LoadedCatalog) -> None:
    errors = KBCatalogService.validate_state_references(catalog)
    if errors:
        preview = "; ".join(errors[:3])
        if len(errors) > 3:
            preview += f"; and {len(errors) - 3} more"
        raise click.ClickException(
            "The KB catalog cannot be executed because mapped files are invalid: " + preview
        )


def _check_applicability(solution: KBSolution, *, version: str, component: str, allow_unverified: bool) -> None:
    if solution.metadata.status not in {"validated", "verified"} and not allow_unverified:
        raise click.ClickException(
            f"Solution '{solution.metadata.id}' has status '{solution.metadata.status}'. "
            "Use --allow-unverified only for controlled development testing."
        )
    service = KBCatalogService()
    if version and not service.version_matches(version, solution.applicability.versions):
        raise click.ClickException(
            f"KB {solution.kb.id} is not mapped for version {version}; supported: "
            f"{', '.join(solution.applicability.versions) or 'all'}"
        )
    if component and not service.component_matches(component, solution.applicability.components):
        raise click.ClickException(
            f"KB {solution.kb.id} is not mapped for component '{component}'; supported: "
            f"{', '.join(solution.applicability.components) or 'all'}"
        )


def _invoke_deploy(
    ctx: click.Context,
    execution: ExecutionMapping,
    *,
    mode: str,
    states_source: Optional[str],
    values_source: Optional[str],
    without_values: bool,
    environment: str,
    version: str,
    values: str,
    values_path: Optional[str],
    salt_env: Optional[str],
    target_group: Optional[str],
    force: bool,
    yes: bool,
    wait: int,
    repository_file: Optional[str],
    work_dir: str,
    refresh: bool,
    show_tree: bool,
) -> None:
    ctx.invoke(
        deploy_command,
        resource=execution.resolved_resource,
        mode=mode,
        states_source=states_source,
        data_source=values_source,
        without_data=without_values or not execution.values_required,
        environment=environment,
        version=version,
        values=values,
        data_path=values_path,
        state_entrypoint=execution.resolved_entrypoint,
        data_mode="runtime",
        salt_env=salt_env,
        remote_path=None,
        target_group=target_group,
        job_name=None,
        save_job=False,
        legacy_create_job=None,
        force=force,
        yes=yes,
        wait=wait,
        repository_file=repository_file,
        work_dir=work_dir,
        refresh=refresh,
        show_tree=show_tree,
    )


@click.group("kb", cls=RichGroup, invoke_without_command=True)
@click.pass_context
def kb_group(ctx: click.Context) -> None:
    """Discover and execute static KB-to-Salt solution mappings."""
    if ctx.invoked_subcommand is None:
        command_header(
            "kb",
            "KB solution catalog",
            description="Search verified KB mappings without exposing Salt implementation details to customers.",
            icon="magnify",
            mode=("STATIC MAPPINGS", "black on #7dd3fc"),
        )
        data_table(
            "Common tasks",
            [("Command", "scc.cmd"), ("Purpose", "scc.value")],
            [
                ["scc kb search <symptom>", "Find KB solutions by symptom, component, error text, or mapped state."],
                ["scc kb show <kb-id>", "Inspect applicability, risk, and the authoritative SLS mapping."],
                ["scc kb validate", "Validate solution YAML and every mapped SLS reference."],
                ["scc kb schema", "Export JSON Schema for catalog authors, CI, and IDE validation."],
                ["scc kb plan <kb-id> ...", "Resolve the mapping and create a no-change Git deployment plan."],
                ["scc kb execute <kb-id> ... --mode dry-run", "Run the mapped resource SLS with test=True."],
            ],
            icon="doc",
        )
        next_steps([
            "Explore fictional examples: `scc kb list --demo`",
            "Create a catalog starter tree: `scc kb scaffold ./kb-catalog-example`",
            "Machine-readable agent input: `scc kb show <kb-id> --json`",
        ])


@kb_group.command("list")
@_catalog_options
@click.option("--component", default="", help="Filter by exact component name.")
@click.option("--version", default="", help="Filter by a supported VCF version.")
@click.option("--status", "statuses", multiple=True, help="Filter by status; may be repeated.")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def kb_list(
    ctx: click.Context,
    states_source: Optional[str],
    catalog_path: Optional[str],
    catalog_file: Optional[str],
    repository_file: Optional[str],
    refresh: bool,
    demo: bool,
    component: str,
    version: str,
    statuses: tuple[str, ...],
    as_json: bool,
) -> None:
    """List static KB solution mappings."""
    catalog, provenance = _load_catalog(
        ctx,
        states_source=states_source,
        catalog_path=catalog_path,
        catalog_file=catalog_file,
        repository_file=repository_file,
        refresh=refresh,
        demo=demo,
        quiet=as_json,
    )
    status_set = {item.lower() for item in statuses} or None
    matches = [item.solution for item in KBCatalogService.search(catalog, component=component, version=version, statuses=status_set)]
    if as_json:
        click.echo(json.dumps({**provenance, **_catalog_payload(catalog), "solutions": [_solution_payload(item) for item in matches]}, indent=2))
        return
    command_header(
        "kb list",
        "Available KB automations",
        description="Mappings are read from a version-controlled catalog and are never generated by the AI agent.",
        icon="doc",
        meta=[("Catalog", str(catalog.path)), ("Version", catalog.version), ("Commit", provenance.get("commit", "-")[:12])],
    )
    if not matches:
        empty_state("No matching KB solutions", "Adjust the component, version, or status filters.", actions=["scc kb search <symptom>"])
        return
    data_table(
        f"KB solutions ({len(matches)})",
        [
            ("KB", "scc.accent"),
            ("Title", "scc.strong"),
            ("Components", "scc.value"),
            ("Versions", "scc.value"),
            ("Status", "scc.success"),
            ("Risk", "scc.warning"),
        ],
        _solution_rows(matches),
        icon="doc",
    )


@kb_group.command("search")
@click.argument("query")
@_catalog_options
@click.option("--component", default="")
@click.option("--version", default="")
@click.option("--status", "statuses", multiple=True)
@click.option("--limit", type=click.IntRange(1, 100), default=10, show_default=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def kb_search(
    ctx: click.Context,
    query: str,
    states_source: Optional[str],
    catalog_path: Optional[str],
    catalog_file: Optional[str],
    repository_file: Optional[str],
    refresh: bool,
    demo: bool,
    component: str,
    version: str,
    statuses: tuple[str, ...],
    limit: int,
    as_json: bool,
) -> None:
    """Search KB IDs, symptoms, errors, components, and mapped states."""
    catalog, provenance = _load_catalog(
        ctx,
        states_source=states_source,
        catalog_path=catalog_path,
        catalog_file=catalog_file,
        repository_file=repository_file,
        refresh=refresh,
        demo=demo,
        quiet=as_json,
    )
    results = KBCatalogService.search(
        catalog,
        query,
        component=component,
        version=version,
        statuses={item.lower() for item in statuses} or None,
    )[:limit]
    if as_json:
        click.echo(json.dumps({
            "query": query,
            "catalog_version": catalog.version,
            "commit": provenance.get("commit"),
            "matches": [
                {"score": item.score, "matched_fields": list(item.matched_fields), "solution": _solution_payload(item.solution)}
                for item in results
            ],
        }, indent=2))
        return
    command_header(
        "kb search",
        f"Solution matches for: {query}",
        description="Search ranking is dynamic; every returned KB-to-SLS mapping remains static catalog data.",
        icon="magnify",
        meta=[("Catalog version", catalog.version), ("Commit", provenance.get("commit", "-")[:12])],
    )
    if not results:
        empty_state(
            "No catalog mapping found",
            "SCC will not guess or substitute an unrelated Salt state.",
            actions=["Add a reviewed solution.yaml through the saltext-vcf pull-request process."],
        )
        return
    rows = [
        [
            f"{item.score:.1f}",
            item.solution.kb.id,
            item.solution.metadata.title,
            ", ".join(item.solution.applicability.components) or "-",
            item.solution.metadata.status,
            ", ".join(item.matched_fields),
        ]
        for item in results
    ]
    data_table(
        f"Matches ({len(rows)})",
        [
            ("Score", "scc.accent"),
            ("KB", "scc.secondary"),
            ("Title", "scc.strong"),
            ("Components", "scc.value"),
            ("Status", "scc.success"),
            ("Matched", "scc.muted"),
        ],
        rows,
        icon="magnify",
    )
    next_steps([f"Inspect the best match: `scc kb show {results[0].solution.kb.id}`"])


@kb_group.command("show")
@click.argument("identifier")
@_catalog_options
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def kb_show(
    ctx: click.Context,
    identifier: str,
    states_source: Optional[str],
    catalog_path: Optional[str],
    catalog_file: Optional[str],
    repository_file: Optional[str],
    refresh: bool,
    demo: bool,
    as_json: bool,
) -> None:
    """Show one KB's static mapping and applicability rules."""
    catalog, provenance = _load_catalog(
        ctx,
        states_source=states_source,
        catalog_path=catalog_path,
        catalog_file=catalog_file,
        repository_file=repository_file,
        refresh=refresh,
        demo=demo,
        quiet=as_json,
    )
    try:
        solution = KBCatalogService.get(catalog, identifier)
    except KBCatalogError as exc:
        raise click.ClickException(str(exc)) from exc
    if as_json:
        click.echo(json.dumps({"catalog": provenance, "catalog_version": catalog.version, "solution": _solution_payload(solution)}, indent=2))
        return
    _render_solution(solution, provenance)
    next_steps([
        f"Create a no-change plan: `scc kb plan {solution.kb.id} --environment <env> --version <version>`",
        f"Safe execution: `scc kb execute {solution.kb.id} --environment <env> --version <version> --target-group <group> --mode dry-run`",
    ])


@kb_group.command("validate")
@_catalog_options
@click.option("--check-states/--no-check-states", default=True, show_default=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def kb_validate(
    ctx: click.Context,
    states_source: Optional[str],
    catalog_path: Optional[str],
    catalog_file: Optional[str],
    repository_file: Optional[str],
    refresh: bool,
    demo: bool,
    check_states: bool,
    as_json: bool,
) -> None:
    """Validate schema, uniqueness, and mapped SLS references."""
    catalog, provenance = _load_catalog(
        ctx,
        states_source=states_source,
        catalog_path=catalog_path,
        catalog_file=catalog_file,
        repository_file=repository_file,
        refresh=refresh,
        demo=demo,
        quiet=as_json,
    )
    errors = KBCatalogService.validate_state_references(catalog) if check_states else []
    payload = {
        "valid": not errors,
        "catalog_version": catalog.version,
        "solutions": len(catalog.solutions),
        "catalog_path": str(catalog.path),
        "commit": provenance.get("commit"),
        "errors": errors,
    }
    if as_json:
        click.echo(json.dumps(payload, indent=2))
    elif errors:
        command_header("kb validate", "KB solution catalog has errors", icon="shield", mode=("INVALID", "white on red"))
        data_table("Validation errors", [("#", "scc.secondary"), ("Problem", "scc.danger")], [[str(i), error] for i, error in enumerate(errors, 1)], icon="warning")
    else:
        result_summary(
            "KB solution catalog is valid",
            message="Schema, unique mappings, and the single referenced SLS per KB passed validation.",
            metrics=[(len(catalog.solutions), "solutions", "primary"), (len(catalog.solutions), "mapped states", "success")],
            details=[("Catalog", str(catalog.path)), ("Version", catalog.version), ("Commit", provenance.get("commit", "-"))],
        )
    if errors:
        raise click.ClickException(f"KB catalog validation failed with {len(errors)} error(s)")


@kb_group.command("schema")
@click.option("--kind", "schema_kind", type=click.Choice(["solution", "catalog"]), default="solution", show_default=True)
@click.option("--output", type=click.Path(dir_okay=False), help="Write the schema to a file instead of stdout.")
def kb_schema(schema_kind: str, output: Optional[str]) -> None:
    """Export the authoritative JSON Schema used by SCC catalog validation."""
    model = KBSolution if schema_kind == "solution" else CatalogIndex
    payload = model.model_json_schema()
    rendered = json.dumps(payload, indent=2) + "\n"
    if output:
        destination = Path(output).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered, encoding="utf-8")
        result_summary(
            f"{schema_kind.title()} schema written",
            details=[("Output", str(destination)), ("Schema title", payload.get("title", model.__name__))],
        )
        return
    click.echo(rendered, nl=False)


@kb_group.command("scaffold")
@click.argument("output", type=click.Path(exists=False), default="kb-catalog-example")
@click.option("--force", is_flag=True, help="Replace an existing output directory.")
def kb_scaffold(output: str, force: bool) -> None:
    """Copy fictional DNS/NTP definitions as a catalog authoring starter."""
    source = _demo_root()
    destination = Path(output).expanduser().resolve()
    if destination.exists():
        if not force:
            raise click.ClickException(f"{destination} already exists; use --force to replace it")
        if destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink()
    shutil.copytree(source, destination)
    result_summary(
        "KB catalog starter created",
        message="The DNS/NTP entries are fictional examples. Replace their IDs, URLs, applicability, and mappings through normal code review.",
        details=[("Output", str(destination)), ("Catalog", str(destination / "solutions" / "catalog.yaml"))],
    )
    next_steps([
        f"Review definitions: `find {destination}/solutions -type f`",
        f"Validate locally: `scc kb validate --catalog-file {destination}/solutions/catalog.yaml`",
        "Move the reviewed solutions/ tree into the saltext-vcf repository.",
    ])


def _plan_or_execute_options(function):  # type: ignore[no-untyped-def]
    options = [
        click.option("--states-source", help="Named reusable-state source containing states and solution catalog."),
        click.option("--catalog-path", help="Catalog path relative to the reusable-state repository."),
        click.option("--values-source", help="Named private customer-values repository."),
        click.option("--without-values", is_flag=True, help="Use reusable defaults and do not load customer values."),
        click.option("--environment", required=True, help="Customer environment or instance selector."),
        click.option("--version", required=True, help="Customer VCF version used for applicability and values lookup."),
        click.option("--component", default="", help="Optional affected component used for applicability validation."),
        click.option("--values", default="", help="Named values selector used by custom repository layouts."),
        click.option("--values-path", help="Explicit values.yaml path inside the customer-values source."),
        click.option("--salt-env", help="RaaS Salt file-server environment."),
        click.option("--target-group", help="RaaS target group; required for execution."),
        click.option("--allow-unverified", is_flag=True, help="Allow draft/community solutions for controlled development only."),
        click.option("--repository-file", type=click.Path(exists=False)),
        click.option("--work-dir", default=".scc/work", show_default=True),
        click.option("--refresh/--no-refresh", default=True, show_default=True),
        click.option("--show-tree/--no-show-tree", default=True, show_default=True),
    ]
    for option in reversed(options):
        function = option(function)
    return function


@kb_group.command("plan")
@click.argument("identifier")
@_plan_or_execute_options
@click.option("--json", "as_json", is_flag=True, help="Emit the resolved solution contract as JSON; does not invoke deploy rendering.")
@click.pass_context
def kb_plan(
    ctx: click.Context,
    identifier: str,
    states_source: Optional[str],
    catalog_path: Optional[str],
    values_source: Optional[str],
    without_values: bool,
    environment: str,
    version: str,
    component: str,
    values: str,
    values_path: Optional[str],
    salt_env: Optional[str],
    target_group: Optional[str],
    allow_unverified: bool,
    repository_file: Optional[str],
    work_dir: str,
    refresh: bool,
    show_tree: bool,
    as_json: bool,
) -> None:
    """Resolve a KB mapping and build no-change deployment plans."""
    catalog, provenance = _load_catalog(
        ctx,
        states_source=states_source,
        catalog_path=catalog_path,
        catalog_file=None,
        repository_file=repository_file,
        refresh=refresh,
        demo=False,
        quiet=as_json,
    )
    try:
        solution = KBCatalogService.get(catalog, identifier)
    except KBCatalogError as exc:
        raise click.ClickException(str(exc)) from exc
    _require_executable_catalog(catalog)
    _check_applicability(solution, version=version, component=component, allow_unverified=allow_unverified)
    if as_json:
        click.echo(json.dumps({
            "catalog": {**provenance, "version": catalog.version, "path": str(catalog.path)},
            "solution": _solution_payload(solution),
            "runtime": {"environment": environment, "version": version, "component": component or None, "target_group": target_group},
        }, indent=2))
        return
    _render_solution(solution, provenance)
    _invoke_deploy(
        ctx,
        solution.execution,
        mode="plan",
        states_source=states_source,
        values_source=values_source,
        without_values=without_values,
        environment=environment,
        version=version,
        values=values,
        values_path=values_path,
        salt_env=salt_env,
        target_group=target_group,
        force=False,
        yes=False,
        wait=1800,
        repository_file=repository_file,
        work_dir=work_dir,
        refresh=refresh,
        show_tree=show_tree,
    )
    next_steps([
        "Review and merge customer configuration through the normal Git approval process.",
        f"Execute safely: `scc kb execute {solution.kb.id} --environment {environment} --version {version} --target-group <group> --mode dry-run`",
    ])


@kb_group.command("execute")
@click.argument("identifier")
@_plan_or_execute_options
@click.option("--mode", type=click.Choice(["dry-run", "apply"]), default="dry-run", show_default=True)
@click.option("--force", is_flag=True, help="Overwrite existing state files in RaaS.")
@click.option("--yes", is_flag=True, help="Skip the typed apply confirmation in trusted automation.")
@click.option("--wait", type=int, default=1800, show_default=True)
@click.pass_context
def kb_execute(
    ctx: click.Context,
    identifier: str,
    states_source: Optional[str],
    catalog_path: Optional[str],
    values_source: Optional[str],
    without_values: bool,
    environment: str,
    version: str,
    component: str,
    values: str,
    values_path: Optional[str],
    salt_env: Optional[str],
    target_group: Optional[str],
    allow_unverified: bool,
    repository_file: Optional[str],
    work_dir: str,
    refresh: bool,
    show_tree: bool,
    mode: str,
    force: bool,
    yes: bool,
    wait: int,
) -> None:
    """Execute the statically mapped resource SLS through a direct RaaS job/JID."""
    if not target_group:
        raise click.ClickException("--target-group is required for KB execution")
    catalog, provenance = _load_catalog(
        ctx,
        states_source=states_source,
        catalog_path=catalog_path,
        catalog_file=None,
        repository_file=repository_file,
        refresh=refresh,
        demo=False,
    )
    try:
        solution = KBCatalogService.get(catalog, identifier)
    except KBCatalogError as exc:
        raise click.ClickException(str(exc)) from exc
    _check_applicability(solution, version=version, component=component, allow_unverified=allow_unverified)
    if mode == "dry-run" and not solution.execution.dry_run_supported:
        raise click.ClickException(f"KB {solution.kb.id} does not declare dry-run support")

    _require_executable_catalog(catalog)
    _render_solution(solution, provenance)
    execution = solution.execution
    if mode == "apply":
        confirmed = confirm_destructive(
            action=f"execute verified KB solution {solution.kb.id}",
            targets_summary=(
                f"Target group: {target_group}; version: {version}; state: {execution.state}; "
                f"catalog commit: {provenance.get('commit', '-')[:12]}; test=False"
            ),
            typed_phrase="apply",
            auto_approve=yes,
        )
        if not confirmed:
            ui_warn("KB execution cancelled before any RaaS publication or state execution.")
            return

    command_header(
        "kb execute",
        "Execute mapped resource state",
        description=execution.description or execution.state,
        icon="gear",
        meta=[("KB", solution.kb.id), ("Mapped state", execution.state), ("Target group", target_group)],
        mode=(("TEST=FALSE" if mode == "apply" else "TEST=TRUE"), "white on red" if mode == "apply" else "black on #e6c75a"),
    )
    _invoke_deploy(
        ctx,
        execution,
        mode=mode,
        states_source=states_source,
        values_source=values_source,
        without_values=without_values,
        environment=environment,
        version=version,
        values=values,
        values_path=values_path,
        salt_env=salt_env,
        target_group=target_group,
        force=force,
        yes=True,
        wait=wait,
        repository_file=repository_file,
        work_dir=work_dir,
        refresh=refresh,
        show_tree=show_tree,
    )

    result_summary(
        "KB solution execution completed",
        message="The single mapped resource state came from the static catalog and used direct RaaS execution with JID tracking.",
        details=[
            ("KB", solution.kb.id),
            ("Solution", solution.metadata.id),
            ("State", execution.state),
            ("Mode", mode),
            ("Target group", target_group),
            ("Catalog version", catalog.version),
            ("Catalog commit", provenance.get("commit", "-")),
        ],
    )


def register(group: click.Group) -> None:
    group.add_command(kb_group)
