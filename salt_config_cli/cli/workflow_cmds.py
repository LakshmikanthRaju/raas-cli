"""High-level Git-to-RaaS workflows.

These commands intentionally hide the low-level sequence from first-time users
while still exposing the selected Git commits, validated files, and every
underlying SCC command for review and automation.
"""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import PurePosixPath
from typing import Optional

import click

from salt_config_cli.core.config import SaltConfigSettings
from salt_config_cli.core.repositories import RepositoryStore
from salt_config_cli.services.git_repository import (
    ContentPackage,
    ContentWorkspaceService,
    GitRepositoryError,
    GitRepositoryService,
)
from salt_config_cli.ui import (
    RichCommand,
    RichGroup,
    command_header,
    confirm_destructive,
    data_table,
    hint as ui_hint,
    kv_table,
    next_steps,
    result_summary,
    spinner,
    success as ui_success,
    warn as ui_warn,
)


def _root_context(ctx: click.Context) -> click.Context:
    return ctx.find_root()


def _root_config_path(ctx: click.Context) -> Optional[str]:
    root = _root_context(ctx)
    return (root.obj or {}).get("config_path") if root.obj else None


def _selected_profile(ctx: click.Context) -> Optional[str]:
    root = _root_context(ctx)
    return (root.obj or {}).get("profile") if root.obj else None


def _repository_store(ctx: click.Context, repository_file: Optional[str]) -> RepositoryStore:
    return RepositoryStore(repository_file, connection_config=_root_config_path(ctx))


def _prepare_package(
    ctx: click.Context,
    *,
    resource: str,
    states_source: Optional[str],
    data_source: Optional[str],
    without_data: bool,
    environment: str,
    version: str,
    values: str,
    data_path: Optional[str],
    state_entrypoint: Optional[str],
    repository_file: Optional[str],
    work_dir: str,
    refresh: bool,
) -> ContentPackage:
    store = _repository_store(ctx, repository_file)
    try:
        states_name, states_config = store.get(states_source, kind="states")
    except ValueError as exc:
        raise click.ClickException(f"{exc}. Run `scc repo setup` first.") from exc

    data_name: Optional[str] = None
    data_config = None
    if not without_data:
        try:
            data_name, data_config = store.get(data_source, kind="data")
        except ValueError:
            if data_source:
                raise
            ui_warn("No customer-values source is configured; continuing with reusable state defaults only.")

    git_service = GitRepositoryService()
    try:
        with spinner(f"Syncing reusable states from {states_name}@{states_config.ref}…"):
            states_repo = git_service.sync(states_name, states_config, refresh=refresh)
        data_repo = None
        if data_name and data_config:
            with spinner(f"Syncing customer values from {data_name}@{data_config.ref}…"):
                data_repo = git_service.sync(data_name, data_config, refresh=refresh)
        with spinner(f"Validating and assembling resource '{resource}'…"):
            package = ContentWorkspaceService(work_dir).build(
                resource,
                states_repo,
                data_repository=data_repo,
                environment=environment,
                version=version,
                values=values,
                data_path=data_path,
                state_entrypoint=state_entrypoint,
            )
        return package
    except (GitRepositoryError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc


def _package_summary(package: ContentPackage) -> dict:
    """Return non-secret plan metadata for display or JSON output.

    This summary is generated in memory. It is intentionally not persisted as
    an approval artifact because the customer's Git review/merge process is the
    source of approval.
    """
    return {
        "resource": package.resource,
        "entrypoint": package.state_entrypoint,
        "states_repository_path": package.states_repository_path,
        "environment": package.environment or None,
        "version": package.version or None,
        "values": package.values or None,
        "states": {
            "source": package.states_source.name,
            "url": package.states_source.source.url,
            "ref": package.states_source.source.ref,
            "commit": package.states_source.commit,
            "committed_at": package.states_source.committed_at,
        },
        "data": (
            {
                "source": package.data_source.name,
                "url": package.data_source.source.url,
                "ref": package.data_source.source.ref,
                "commit": package.data_source.commit,
                "committed_at": package.data_source.committed_at,
                "repository_path": package.data_repository_path,
            }
            if package.data_source
            else None
        ),
        "files": [
            {
                "type": item.file_type,
                "path": item.path,
                "sha256": item.sha256,
                "size": item.size,
            }
            for item in package.files
        ],
        "warnings": list(package.warnings),
    }


def _deploy_command_text(
    resource: str,
    *,
    mode: str,
    environment: str,
    version: str,
    values: str,
    data_path: Optional[str],
    state_entrypoint: Optional[str],
    data_mode: str,
    target_group: Optional[str],
    states_source: Optional[str],
    data_source: Optional[str],
    without_data: bool,
) -> str:
    parts = ["scc", "deploy", resource, "--mode", mode]
    options = [
        ("--environment", environment),
        ("--version", version),
        ("--values", values),
        ("--values-path", data_path or ""),
        ("--entrypoint", state_entrypoint or ""),
        ("--values-mode", data_mode),
        ("--target-group", target_group or "<group>"),
        ("--states-source", states_source or ""),
        ("--values-source", data_source or ""),
    ]
    for flag, value in options:
        if value:
            parts.extend([flag, value])
    if without_data:
        parts.append("--without-data")
    return " ".join(shlex.quote(part) if part != "<group>" else part for part in parts)


def _render_plan(package: ContentPackage, *, as_json: bool = False) -> None:
    summary = _package_summary(package)
    if as_json:
        click.echo(json.dumps(summary, indent=2))
        return

    state_info = summary.get("states") or {}
    data_info = summary.get("data") or {}
    command_header(
        "deploy plan",
        f"Deployment plan: {package.resource}",
        description="Git content is resolved to exact commits, validated, and staged locally. No RaaS changes have been made.",
        icon="shield",
        meta=[
            ("State commit", str(state_info.get("commit", ""))[:12]),
            ("Values commit", str(data_info.get("commit", ""))[:12] if data_info else "defaults only"),
            ("Entrypoint", package.state_entrypoint),
        ],
        mode=("PLAN ONLY", "black on #e6c75a"),
    )
    kv_table(
        "Git provenance",
        [
            ("Resource", package.resource),
            ("Reusable state source", f"{state_info.get('source')}@{state_info.get('ref')}"),
            ("State repository path", package.states_repository_path),
            ("State commit", state_info.get("commit", "-")),
            ("Customer values source", f"{data_info.get('source')}@{data_info.get('ref')}" if data_info else "not used"),
            ("Values commit", data_info.get("commit", "-") if data_info else "-"),
            ("Local workspace", str(package.workspace)),
            ("Customer values path", package.data_repository_path or "not used"),
        ],
    )
    rows = []
    for item in summary.get("files", []):
        rows.append(
            [
                item.get("type", ""),
                item.get("path", ""),
                str(item.get("size", 0)),
                str(item.get("sha256", ""))[:12],
            ]
        )
    data_table(
        f"Selected content ({len(rows)} files)",
        [
            ("Type", "scc.secondary"),
            ("Path", "scc.value"),
            ("Bytes", "scc.muted"),
            ("SHA-256", "scc.accent"),
        ],
        rows,
        icon="doc",
        caption="The exact Git commits and files above will be used for publication or execution.",
    )
    for warning in package.warnings:
        ui_warn(warning)
    result_summary(
        "Deployment plan ready",
        status="success",
        message="Review the selected commits and files above. Publishing and execution require an explicit mode.",
        metrics=[(len(rows), "files", "primary"), (len(package.warnings), "warnings", "warning")],
    )


@click.group("workflow", cls=RichGroup, invoke_without_command=True)
@click.pass_context
def workflow_group(ctx: click.Context) -> None:
    """Simple, reviewable Git-to-RaaS deployment workflows."""
    if ctx.invoked_subcommand is None:
        command_header(
            "workflow",
            "Git-to-RaaS in four clear steps",
            description="SCC keeps the reusable state repo, private values repo, RaaS publication, and execution traceable but simple.",
            icon="rocket",
        )
        data_table(
            "Recommended path",
            [("Step", "scc.secondary"), ("Command", "scc.cmd"), ("What it does", "scc.value")],
            [
                ["1", "scc repo setup", "Configure public/shared states and private customer values without storing secrets."],
                ["2", "scc deploy <resource>", "Sync Git, validate YAML/content, resolve commits, and show a no-change plan."],
                ["3", "scc deploy <resource> --mode dry-run ...", "Publish the state tree and execute directly with test=True plus runtime values."],
                ["4", "scc deploy <resource> --mode apply ...", "Confirm the target and commits, then execute directly with test=False."],
            ],
            icon="rocket",
        )
        next_steps(["Interactive tutorial: `scc tutorial gitops`", "Detailed help: `scc help deploy`"])


@workflow_group.command("plan")
@click.argument("resource")
@click.option("--states-source", help="Named states source; defaults to the configured states source.")
@click.option("--values-source", "--data-source", "data_source", help="Named customer-values source; defaults to the configured values source.")
@click.option("--without-data", is_flag=True, help="Use reusable defaults only; do not load customer values.")
@click.option("--environment", default="", help="Customer environment or instance name, such as prod or site-a.")
@click.option("--version", default="", help="Version selector used by the values-source layout, such as 9.1.1.")
@click.option("--values", default="", help="Named values file selector for layouts using {values}.")
@click.option("--values-path", "--data-path", "data_path", help="Explicit values.yaml path inside the values source, overriding its layout.")
@click.option("--entrypoint", "state_entrypoint", help="Specific .sls file inside the resource folder; normally discovered automatically.")
@click.option("--repository-file", type=click.Path(exists=False), help="Use another repositories.yaml file.")
@click.option("--work-dir", default=".scc/work", show_default=True, help="Local review workspace.")
@click.option("--refresh/--no-refresh", default=True, show_default=True, help="Fetch the configured Git refs before planning.")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def workflow_plan(
    ctx: click.Context,
    resource: str,
    states_source: Optional[str],
    data_source: Optional[str],
    without_data: bool,
    environment: str,
    version: str,
    values: str,
    data_path: Optional[str],
    state_entrypoint: Optional[str],
    repository_file: Optional[str],
    work_dir: str,
    refresh: bool,
    as_json: bool,
) -> None:
    """Create a local validated deployment plan without contacting RaaS."""
    package = _prepare_package(
        ctx,
        resource=resource,
        states_source=states_source,
        data_source=data_source,
        without_data=without_data,
        environment=environment,
        version=version,
        values=values,
        data_path=data_path,
        state_entrypoint=state_entrypoint,
        repository_file=repository_file,
        work_dir=work_dir,
        refresh=refresh,
    )
    _render_plan(package, as_json=as_json)
    if not as_json:
        suffix = ""
        if environment:
            suffix += f" --environment {environment}"
        if version:
            suffix += f" --version {version}"
        next_steps(
            [
                f"Publish the reusable state tree: `scc deploy {resource}{suffix} --mode publish`",
                f"Publish and run test=True directly: `scc deploy {resource}{suffix} --mode dry-run --target-group <group>`",
                "Use the customer Git pull-request and protected-branch process for content approval.",
            ]
        )


@click.command("deploy", cls=RichCommand)
@click.argument("resource")
@click.option(
    "--mode",
    type=click.Choice(["plan", "publish", "dry-run", "apply"], case_sensitive=False),
    default="plan",
    show_default=True,
    help="plan=no RaaS changes; publish=upload states; dry-run=direct test=True; apply=direct test=False.",
)
@click.option("--states-source", help="Named reusable-state source.")
@click.option("--values-source", "--data-source", "data_source", help="Named customer-values source.")
@click.option("--without-data", is_flag=True, help="Use state defaults only.")
@click.option("--environment", default="", help="Environment/instance selector used by the values-source layout.")
@click.option("--version", default="", help="Version selector used by the values-source layout.")
@click.option("--values", default="", help="Named values selector used by {values} layouts.")
@click.option("--values-path", "--data-path", "data_path", help="Explicit values.yaml path inside the private values source.")
@click.option("--entrypoint", "state_entrypoint", help="Specific .sls file inside the resource folder; used by catalog workflows and advanced users.")
@click.option("--values-mode", "--data-mode", "data_mode", type=click.Choice(["runtime", "pillar", "none"]), default="runtime", show_default=True, help="runtime passes values as execution-scoped pillar; pillar explicitly persists them in RaaS; none ignores values.")
@click.option("--salt-env", help="RaaS Salt file-server environment; defaults to the active connection profile.")
@click.option("--remote-path", help="Remote state folder; defaults to the repository path, such as /vcf-infra/<resource>.")
@click.option("--target-group", help="Existing RaaS target group used for direct execution.")
@click.option("--job-name", help="Optional saved-job name; defaults to <resource>-<environment>-job.")
@click.option("--save-job/--no-save-job", default=False, show_default=True, help="Optionally create/update a reusable saved job, pinned to test=False. Direct execution is the default.")
@click.option("--create-job/--no-create-job", "legacy_create_job", default=None, hidden=True, help="Deprecated alias for --save-job/--no-save-job.")
@click.option("--force", is_flag=True, help="Overwrite state files already present in RaaS.")
@click.option("--yes", is_flag=True, help="Skip interactive confirmations, including apply. Use only in trusted automation.")
@click.option("--wait", type=int, default=1800, show_default=True, help="Seconds to wait for dry-run/apply completion; 0 waits indefinitely.")
@click.option("--repository-file", type=click.Path(exists=False))
@click.option("--work-dir", default=".scc/work", show_default=True)
@click.option("--refresh/--no-refresh", default=True, show_default=True)
@click.option("--show-tree/--no-show-tree", default=True, show_default=True)
@click.pass_context
def deploy_command(
    ctx: click.Context,
    resource: str,
    mode: str,
    states_source: Optional[str],
    data_source: Optional[str],
    without_data: bool,
    environment: str,
    version: str,
    values: str,
    data_path: Optional[str],
    state_entrypoint: Optional[str],
    data_mode: str,
    salt_env: Optional[str],
    remote_path: Optional[str],
    target_group: Optional[str],
    job_name: Optional[str],
    save_job: bool,
    legacy_create_job: Optional[bool],
    force: bool,
    yes: bool,
    wait: int,
    repository_file: Optional[str],
    work_dir: str,
    refresh: bool,
    show_tree: bool,
) -> None:
    """Plan, publish, and safely execute a Git-backed Salt resource.

    The default is a no-change plan. Use --mode dry-run for the normal first
    direct execution and --mode apply only after the customer Git change is
    approved, merged, and the dry-run result has been reviewed. SCC does not
    create a persistent saved job unless --save-job is explicitly requested.
    That saved job is pinned to test=False - it applies for real every time
    it's run via `scc job-run`.

    Examples:
      $ scc deploy dns --environment prod --version 9.1.1
      $ scc deploy dns --environment prod --version 9.1.1 --mode dry-run --target-group vcf-prod
      $ scc deploy dns --environment prod --version 9.1.1 --mode apply --target-group vcf-prod
    """
    mode = mode.lower()
    if legacy_create_job is not None:
        save_job = legacy_create_job
        ui_warn("--create-job/--no-create-job is deprecated; use --save-job/--no-save-job.")
    if data_mode == "none":
        without_data = True
    package = _prepare_package(
        ctx,
        resource=resource,
        states_source=states_source,
        data_source=data_source,
        without_data=without_data,
        environment=environment,
        version=version,
        values=values,
        data_path=data_path,
        state_entrypoint=state_entrypoint,
        repository_file=repository_file,
        work_dir=work_dir,
        refresh=refresh,
    )
    _render_plan(package)
    if mode == "plan":
        dry_run = _deploy_command_text(
            resource,
            mode="dry-run",
            environment=environment,
            version=version,
            values=values,
            data_path=data_path,
            state_entrypoint=state_entrypoint,
            data_mode=data_mode,
            target_group=target_group,
            states_source=states_source,
            data_source=data_source,
            without_data=without_data,
        )
        next_steps(
            [
                "Approve and merge customer values through the repository's normal pull-request process.",
                f"Continue with a safe test execution: `{dry_run}`",
            ]
        )
        return

    if mode in {"dry-run", "apply"} and not target_group:
        raise click.ClickException("--target-group is required for dry-run and apply")
    if save_job and not target_group:
        raise click.ClickException("--target-group is required when --save-job is enabled")
    if data_mode == "pillar" and package.data_file is None:
        raise click.ClickException("--values-mode pillar requires a customer values file")

    apply_confirmed = False
    if mode == "apply":
        state_commit = package.states_source.commit[:12]
        data_commit = package.data_source.commit[:12] if package.data_source else "defaults only"
        apply_confirmed = confirm_destructive(
            action=f"apply Git-backed Salt resource '{resource}'",
            targets_summary=(
                f"Target group: {target_group}; state commit: {state_commit}; "
                f"values commit: {data_commit}; test=False"
            ),
            typed_phrase="apply",
            auto_approve=yes,
        )
        if not apply_confirmed:
            ui_warn("Apply cancelled before any RaaS files, runtime values, saved jobs, or execution were changed.")
            return

    settings = SaltConfigSettings.load_from_file(_root_config_path(ctx), _selected_profile(ctx))
    selected_salt_env = salt_env or settings.default_environment or "base"
    destination = remote_path or f"/{package.states_repository_path.strip('/')}"
    selected_job_name = job_name or "-".join(
        part for part in (resource, environment or values or "default", "job") if part
    )
    entrypoint_path = PurePosixPath(package.state_entrypoint)
    try:
        entrypoint_relative = entrypoint_path.relative_to(PurePosixPath(package.resource))
    except ValueError:
        entrypoint_relative = PurePosixPath(entrypoint_path.name)
    remote_state_file = str(PurePosixPath(destination) / entrypoint_relative)
    state_ref = remote_state_file.removesuffix(".sls").lstrip("/").replace("/", ".")

    # Low-level command references are injected at registration time.
    commands = (ctx.find_root().obj or {}).get("workflow_commands", {})
    upload_command = commands.get("upload")
    pillar_command = commands.get("upload_pillar")
    job_create_command = commands.get("job_create")
    run_state_command = commands.get("run_state")
    if not all((upload_command, pillar_command, job_create_command, run_state_command)):
        raise click.ClickException("Workflow command integration is unavailable in this build")

    ui_success(f"Publishing state commit {package.states_source.commit[:12]} to {selected_salt_env}{destination}")
    ctx.invoke(
        upload_command,
        source=str(package.states_dir),
        path=destination,
        saltenv=selected_salt_env,
        force=force,
        include=(),
        exclude=(),
        assume_yes=yes or apply_confirmed,
        show_tree=show_tree,
    )

    if data_mode == "pillar" and package.data_file:
        pillar_name = "-".join(part for part in (resource, environment or values or "values") if part)
        ctx.invoke(
            pillar_command,
            local_file=str(package.data_file),
            name=pillar_name,
            description=(
                f"Managed by SCC from {package.data_source.name if package.data_source else 'values source'} "
                f"commit {package.data_source.commit[:12] if package.data_source else '-'}"
            ),
            target_group=target_group,
            refresh=mode in {"dry-run", "apply"},
            target="*",
            target_type="glob",
        )
    elif data_mode == "runtime" and package.data_file:
        ui_hint("Customer values will be passed as execution-scoped pillar; they are not uploaded to the file server or persisted in RaaS.")

    if save_job:
        description = (
            f"SCC reusable job: {resource}; state commit {package.states_source.commit[:12]}. "
            "Customer values are supplied only at direct execution time."
        )
        ctx.invoke(
            job_create_command,
            name=selected_job_name,
            cmd="state.apply",
            target=None,
            target_group=target_group,
            args=(state_ref,),
            kwargs=("test=False",),
            pillars=(),
            saltenv=selected_salt_env,
            desc=description,
            state=None,
            cmd_type="local",
            masters=(),
            inputs=(),
        )
        ui_warn(
            "The saved job was persisted with test=False - it will apply for real every time "
            "it's run via `scc job-run`. Treat it with the same care as `--mode apply`."
        )

    if mode in {"dry-run", "apply"}:
        runtime_values_file = (
            str(package.data_file) if data_mode == "runtime" and package.data_file else None
        )
        ctx.invoke(
            run_state_command,
            state_file=remote_state_file,
            target=None,
            target_group=target_group,
            target_type="glob",
            saltenv=selected_salt_env,
            test=mode == "dry-run",
            yes=True,
            run_async=False,
            wait=wait,
            as_json=False,
            pillar=None,
            pillar_file=runtime_values_file,
        )

    result_summary(
        "Git-to-RaaS workflow complete",
        status="success",
        message=(
            "The selected Git content was published and executed in test mode. Review results before apply."
            if mode == "dry-run"
            else "The selected reusable state content was published to the RaaS file server."
            if mode == "publish"
            else "The selected Git content was applied after SCC safety confirmation."
        ),
        details=[
            ("Resource", resource),
            ("Mode", mode),
            ("Salt environment", selected_salt_env),
            ("Target group", target_group or "-"),
            ("Execution", "direct state.apply" if mode in {"dry-run", "apply"} else "not executed"),
            ("Saved job", selected_job_name if save_job else "not created"),
            ("RaaS state path", remote_state_file),
            ("State commit", package.states_source.commit),
            ("Values commit", package.data_source.commit if package.data_source else "defaults"),
            ("Customer values path", package.data_repository_path or "not used"),
        ],
    )
    if mode == "dry-run":
        apply_command = _deploy_command_text(
            resource,
            mode="apply",
            environment=environment,
            version=version,
            values=values,
            data_path=data_path,
            state_entrypoint=state_entrypoint,
            data_mode=data_mode,
            target_group=target_group,
            states_source=states_source,
            data_source=data_source,
            without_data=without_data,
        )
        next_steps(
            [
                "Review the per-minion dry-run result and ensure the customer Git change is approved and merged.",
                f"Apply the currently configured Git refs after confirming the displayed commits: `{apply_command}`",
            ]
        )


# Also expose the same command under `scc workflow deploy`.
workflow_group.add_command(deploy_command, name="deploy")


def register(
    group: click.Group,
    *,
    upload_command: click.Command,
    upload_pillar_command: click.Command,
    job_create_command: click.Command,
    run_state_command: click.Command,
) -> None:
    group.add_command(workflow_group)
    group.add_command(deploy_command, name="deploy")
    # The root object is initialized at runtime by `cli`; wrap its callback so
    # command references are available after Click creates the context object.
    original_callback = group.callback

    def callback_with_workflow_commands(*args, **kwargs):  # type: ignore[no-untyped-def]
        result = original_callback(*args, **kwargs) if original_callback else None
        ctx = click.get_current_context(silent=True)
        if ctx is not None:
            ctx.ensure_object(dict)
            ctx.obj["workflow_commands"] = {
                "upload": upload_command,
                "upload_pillar": upload_pillar_command,
                "job_create": job_create_command,
                "run_state": run_state_command,
            }
        return result

    group.callback = callback_with_workflow_commands
