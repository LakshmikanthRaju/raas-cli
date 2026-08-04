# Changelog

## 0.8.2

- Added a concrete `scc tutorial dns` customer journey covering repository setup, access validation, plan, direct `test=True` execution, and confirmed apply.
- Added `scc tutorial kb-search` for searching the static `saltext-vcf` KB catalog by symptom or ID, reviewing the mapped SLS, planning, dry-running, and applying.
- Clarified in the tutorials that only reusable state files are published to the RaaS file server; customer `values.yaml` is supplied as execution-scoped pillar and no persistent saved job is created.
- Added `docs/CUSTOMER_JOURNEYS.md` and linked the recommended tutorials from the main README and general walkthrough.
- Added regression coverage for themed/plain tutorial rendering, concrete DNS commands, static catalog ownership, and removal of previously rejected terminology and workflow artifacts.

## 0.8.1

- Simplified each KB solution to one static `execution.state` mapping instead of precheck/remediation/postcheck arrays.
- Preserved the existing resource layout: `<resource>.sls`, `default.yaml`, and `map.jinja`; removed demo `validate.sls` and `configure.sls` files.
- Made SCC derive the resource folder and SLS entrypoint from the dotted state while retaining optional overrides for non-standard repositories.
- Simplified `scc kb show/plan/execute` to display, plan, and directly execute one resource state with runtime customer values.
- Removed the `--include-checks` / `--remediation-only` execution option and multi-step workflow rendering.
- Updated DNS/NTP examples, schemas, tutorials, catalog authoring documentation, and regression tests.
- Retained read compatibility for a legacy catalog index containing one `remediation_states` entry.

## 0.8.0

- Added a static, Git-versioned KB-to-SLS solution catalog with schema-validated `solution.yaml` definitions and a searchable `solutions/catalog.yaml` index.
- Added themed `scc kb list/search/show/validate/plan/execute/scaffold` commands and clean JSON contracts for Config AI Agent integration.
- Added applicability checks for component, VCF version, verification status, dry-run support, and catalog consistency before execution.
- Added validation for duplicate mappings, stale index metadata, missing values schemas, missing SLS files, and state/entrypoint mismatches.
- Added `--entrypoint` support to `scc deploy` so catalog workflows can select an exact reviewed `.sls` file inside a reusable resource.
- KB execution reuses direct RaaS execution: reusable states go to the file server, customer `values.yaml` is passed as runtime pillar, and every step is tracked by a normal RaaS JID. No persistent saved job is created.
- Added fictional DNS and NTP catalog examples, values schemas, sample states, sample customer values, and `scc kb scaffold` for open-source authors.
- Added a network-free `scc tutorial kb` walkthrough and retained all previous profile, theme, Git, direct-execution, and formatting behavior.

## 0.7.2

- Changed `scc deploy` to execute `state.apply` directly by default instead of creating and running a persistent saved job.
- Added explicit `--save-job` for customers who want a reusable RaaS job; saved jobs are always created with `test=True` and never contain customer values.
- Customer `values.yaml` content is passed as execution-scoped pillar data for dry-run/apply and is never uploaded to the RaaS file server.
- Added the preferred customer-values layout `{environment}/{version}/{resource}/values.yaml` while preserving older layouts.
- Preserved the open-source repository path when publishing states, for example `vcf-infra/cluster-drs` becomes `/vcf-infra/cluster-drs` in the selected RaaS file-server environment.
- Added direct-execution, values-layout, safe saved-job, and RaaS-path regression tests.

## 0.7.1

- Removed the `--approved-manifest` option and stopped generating `release.yaml`.
- Made the customer Git pull-request, branch-protection, and merge process the single content-approval mechanism.
- Simplified `scc deploy`: plan displays exact commits and validated files, dry-run executes `test=True`, and apply refreshes the configured refs, displays commits and target group, then requires explicit confirmation.
- Retained commit/file-hash visibility in plan output and JSON without persisting a separate approval artifact.
- Updated the launch dashboard, examples, tutorials, architecture, security guidance, and customer onboarding to the simplified workflow.
- Added regression coverage proving the removed option is rejected, no release artifact is written, refreshed commits are displayed, and apply can still be cancelled before any RaaS mutation.

## 0.7.0

- Build review workspaces atomically so repeat plans cannot retain stale customer data.
- Require apply confirmation before any RaaS publication or saved-job mutation.
- Reject embedded/query-string Git credentials and fail early when explicit token authentication has no secure credential.
- Clean ignored/untracked cache files during Git refresh and validate resource/environment/version selectors.

- Replaced the basic GitHub raw-file integration with a generic system-Git service supporting HTTPS, SSH, local mirrors, GitHub Enterprise, GitLab, Bitbucket, branches, tags, and commit SHAs.
- Added a separate non-secret `repositories.yaml` catalog so Git source metadata no longer belongs in RaaS connection profiles.
- Added `scc repo setup/add/list/show/use/test/sync/login/logout/import/export/remove/path` with OS-keychain, SSH-agent, Git credential-helper, and source-specific environment credential support.
- Added a high-level `scc deploy` workflow that combines Git synchronization, recursive state validation, private data resolution, RaaS file-server publication, saved-job creation, target-group execution, and live dry-run/apply results.
- Added immutable `release.yaml` provenance with exact state/data commits, selected repository paths, entrypoint, file sizes, and SHA-256 hashes.
- Required `--approved-manifest` for apply and reject execution when the current commits, metadata, file list, sizes, or hashes differ from the approved release.
- Made runtime-only private data injection the default; persistent RaaS pillar publication is an explicit `--data-mode pillar` choice.
- Reworked tutorials, examples, dashboard actions, and documentation around a four-step plan → dry-run → approval → immutable apply journey.
- Retained `configure-git`, `pull`, and `pull-data` as compatibility commands backed by the new generic Git/cache layer.
- Added bounded Git timeouts, stale cache-lock recovery, SSH batch mode, URL/ref/path validation, recursive content limits, symlink rejection, UTF-8/YAML validation, atomic owner-only metadata writes, and a fixed Click usage-error compatibility path.
- Added regression tests for legacy Git migration, local Git synchronization, recursive content, repository import, plan generation, approval enforcement, and changed-content rejection.

## 0.6.1

- Fixed profile loading for hybrid configuration files containing both the v2 `profiles` section and legacy top-level connection fields.
- Added safe automatic migration to the v2 profile schema with a one-time `.pre-v2.bak` backup.
- Fixed `scc profile`, `scc config`, and `scc theme` so invoking a group without a subcommand displays themed help with exit code 0 instead of wrapping help inside an error panel.
- Added responsive record cards for dense tables on narrow terminals while retaining compact professional tables on wider terminals.
- Improved command-header metadata layout for narrow, normal, and ultra-wide terminal sizes.
- Added concise profile-validation messages without raw Pydantic trace URLs.
- Refreshed the SCC launch presentation with a compact product tagline while retaining all selectable themes and plain mode.
- Added regression coverage for the exact reported profile migration, group-help, terminal-layout, and validation failures.

## 0.6.0

- Added runtime-selectable professional terminal themes: Ocean, Enterprise, Graphite, Forest, Amber, High Contrast, and Plain.
- Added themed `scc theme list/current/preview/use/enable/disable/reset` workflows.
- Added global theme persistence with optional per-profile overrides.
- Added one-command `--theme` selection and `SCC_THEME` automation override.
- Added true plain mode with conventional Click help, unboxed command headers, ASCII tables, static progress, and no decorative icons or colours.
- Added `none` and `off` aliases for one-command plain output.
- Added theme-aware help, launch dashboard, status, summaries, tables, spinners, progress trackers, warnings, and errors.
- Added theme fields to configuration inspection and `scc config set`.
- Added regression coverage for theme persistence, precedence, profile overrides, plain mode, previews, and re-enabling enhanced UX.

## 0.5.0

- Restored named connection profiles from the initial production rebuild and integrated them with the themed SCC UX.
- Added global `--profile` / `SCC_PROFILE` and `--config-file` / `SCC_CONFIG` selection for every command.
- Added themed `scc configure`, `scc profile list/show/use/login/logout/test/edit/clone/delete/export/import`, and `scc config show/path/validate/env/set/unset` workflows.
- Enhanced `scc connect --name <profile>` to create or update a named profile while keeping credentials outside YAML.
- Added OS-keychain support for both password and CSP-token profiles.
- Added active-profile context to the launch screen, command headers, status view, and interactive shell.
- Preserved backward compatibility with legacy flat `config.yaml` files and automatic in-memory migration to the `default` profile.
- Added profile-safe import/export, config validation, environment override visibility, and profile-aware shell execution.
- Added regression coverage for profile creation, selection, migration, config mutation, and named connect flows.

## 0.4.0

- Added fully themed `scc help`, `scc --help`, `scc help <command>`, and `<command> --help` views.
- Added command-specific syntax, categorized options, defaults, safety guidance, examples, and related-command panels.
- Unified command responses with command identity cards, metadata, Rich tables, empty states, result summaries, and next-step panels.
- Enhanced status, resource discovery, file-server, pillar, target-group, saved-job, Salt exec, state-run, system-info, and job-result experiences.
- Changed `scc exec` to interactive Rich text output by default; YAML and JSON remain available explicitly for automation.
- Rebuilt `scc shell` with numbered quick operations, Tab completion, persistent history, autosuggestions, timing, and consistent error rendering.
- Added themed top-level handling for usage errors, Click exceptions, cancellation, interruption, and unexpected failures.
- Added missing theme aliases used by tables, trees, subtitles, and strong values.
- Added UX regression coverage; the release suite now contains 49 passing tests.

## 0.3.1

- Fixed `scc status` when rendering ordered key/value row lists.
- Added all icon aliases used by the CLI, including `plug`, `shield`, `spinner`, and failure/warning glyphs.
- Normalized badge style aliases so Rich can render status badges safely.
- Added regression tests for `scc status` and `scc connect --no-test`.
- Added Python 3.14 package classifier and validated the command surface on modern Python.

## 0.3.0

- Restored the feature-rich SCC launch dashboard from the earlier demo.
- Reintroduced grouped command discovery, search, examples, tutorial, and friendly command help.
- Restored recursive file-server browsing, download, upload preview, upload, and edit workflows.
- Restored saved-job creation, live execution, status, and result rendering.
- Restored compliance/drift result presentation and live per-minion progress.
- Added an interactive command launcher, RaaS system information, and guarded raw RPC access.
- Rebuilt the missing `salt_config_cli.ui` and `salt_config_cli.cli.discovery` modules that previously prevented startup.
- Changed state execution to safe dry-run by default; applying changes requires `--no-test` and confirmation.
- Added confirmation for potentially mutating saved jobs.
- Removed embedded workspace data and sanitized all bundled credentials and environment-specific examples.
- Added open-source governance, CI, release validation, architecture, compatibility, and safety documentation.

## 0.1.0

- Initial desired-state, RaaS operations, and demo-oriented implementation.
