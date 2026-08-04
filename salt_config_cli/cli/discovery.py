"""Command discovery and guided learning commands.

These commands are intentionally network-free so a new user can explore SCC
before configuring a RaaS endpoint.
"""
from __future__ import annotations

import textwrap
from collections import defaultdict
from typing import Any

import click
from rich import box
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from salt_config_cli.ui import ICONS, RichGroup, next_steps, section
from salt_config_cli.ui.theme import console, is_plain


CATEGORY_BY_COMMAND = {
    "init": "Getting started", "connect": "Getting started", "configure": "Getting started",
    "profile": "Profiles & configuration", "config": "Profiles & configuration", "login": "Getting started",
    "status": "Getting started", "doctor": "Getting started", "completion": "Getting started",
    "shell": "Getting started", "system-info": "Getting started",
    "list": "Browse RaaS", "fs-list": "Browse RaaS", "pillar-list": "Browse RaaS",
    "target-group-list": "Browse RaaS", "job-list": "Browse RaaS", "show": "Browse RaaS",
    "exec": "Salt operations", "run": "Salt operations", "refresh": "Salt operations",
    "upload-module": "Salt operations", "pillar-refresh": "Salt operations",
    "job-create": "Saved jobs", "job-run": "Saved jobs", "job-status": "Saved jobs",
    "job-results": "Saved jobs", "job-delete": "Saved jobs",
    "upload": "File server", "download": "File server", "edit": "File server", "import": "File server",
    "target-group-create": "Targeting & pillar", "pillar-assign": "Targeting & pillar",
    "upload-pillar": "Targeting & pillar",
    "plan": "Desired state", "apply": "Desired state", "validate": "Desired state",
    "drift": "Desired state", "remediate": "Desired state", "destroy": "Desired state",
    "clear-cache": "Session", "disconnect": "Session", "logout": "Session", "rpc": "Expert",
    "commands": "Discovery", "search": "Discovery", "examples": "Discovery",
    "tutorial": "Discovery", "help": "Discovery",
    "repo": "Git content", "configure-git": "Git content",
    "pull": "Git content", "pull-data": "Git content",
    "workflow": "Git-to-RaaS", "deploy": "Git-to-RaaS",
    "kb": "KB solutions",
}

EXAMPLES: list[tuple[str, str, list[str]]] = [
    (
        "Connect and inspect",
        "Configure a workspace, verify connectivity, then browse server content.",
        [
            "scc configure --name lab",
            "scc profile login lab",
            "scc profile test lab",
            "scc status",
            "scc list",
            "scc fs-list --env base",
        ],
    ),
    (
        "Fleet settings content",
        "Mirror an environment locally, edit it, and upload only reviewed files.",
        [
            "scc fs-list --env fleet_mgmt",
            "scc download /fleet_settings --output ./fleet_settings --env fleet_mgmt",
            "scc upload ./fleet_settings --path /fleet_settings --env fleet_mgmt --force --yes",
        ],
    ),
    (
        "Safe state workflow",
        "Run a state in test mode first, review the result, then apply it.",
        [
            "scc run /fleet_settings/states/fleet.sls --target '*' --env fleet_mgmt --test",
            "scc run /fleet_settings/states/fleet.sls --target '*' --env fleet_mgmt",
        ],
    ),
    (
        "Saved job workflow",
        "Create a reusable job, run it, and fetch results again by JID.",
        [
            "scc job-create fleet-settings-check --function state.apply --arg fleet_settings.fleet --env fleet_mgmt --target-group 'Fleet Mgmt Group' --kwarg test=true",
            "scc job-run fleet-settings-check",
            "scc job-results <jid>",
        ],
    ),
    (
        "Git-backed Salt deployment",
        "Sync reusable states and customer values, preview the selected commits, then dry-run and apply.",
        [
            "scc repo setup",
            "scc repo test --all",
            "scc deploy dns --environment prod --version 9.1.1",
            "scc deploy dns --environment prod --version 9.1.1 --mode dry-run --target-group vcf-prod",
            "scc deploy dns --environment prod --version 9.1.1 --mode apply --target-group vcf-prod",
        ],
    ),
    (
        "KB-guided configuration resolution",
        "Search a static reviewed KB catalog, inspect the mapped SLS workflow, then run a safe dry-run.",
        [
            'scc kb search "DNS lookup failed" --component "NSX Manager" --version 9.1.1',
            "scc kb show KB-123456",
            "scc kb plan KB-123456 --environment prod --version 9.1.1",
            "scc kb execute KB-123456 --environment prod --version 9.1.1 --target-group prod-nsx --mode dry-run",
        ],
    ),
    (
        "Drift and remediation",
        "Compare declarative resources and apply only after reviewing the plan.",
        [
            "scc validate",
            "scc drift",
            "scc remediate --dry-run",
            "scc remediate",
        ],
    ),
]


TOPIC_TUTORIALS: dict[str, dict[str, Any]] = {
    "connect": {
        "intro": "scc connect walkthrough",
        "summary": "One-shot setup: connect to a RaaS server and remember it.",
        "steps": [
            (
                "1. Connect and save in one step",
                "Prompts for server URL, username, and password (masked), tests the connection, then saves everything - the password goes to the OS keychain, never the config file.",
                "scc connect --name <name>",
            ),
            (
                "2. Self-signed certificate error",
                "A lab/internal RaaS server with a self-signed cert fails the live test with CERTIFICATE_VERIFY_FAILED. Disable verification for that profile rather than passing --insecure on every command.",
                "scc config set ssl_verify false --profile <name>",
            ),
            (
                "3. Make it the active profile",
                "Commands use the active profile unless --profile overrides it. scc connect does this by default (--no-make-default to opt out).",
                "scc profile use <name>",
            ),
            (
                "4. Re-verify anytime without reconnecting",
                "Useful after a password rotation or when a run starts failing with auth errors.",
                "scc profile test <name>",
            ),
            (
                "5. Add a second server without losing the first",
                "Each --name is an independent saved profile; connecting to a new one doesn't overwrite others.",
                "scc connect --name <other-name> --no-make-default",
            ),
        ],
        "next_steps": [
            "Manage saved profiles: `scc tutorial profile`",
            "Configure Git sources next: `scc tutorial repo`",
            "Quick health check: `scc status`",
        ],
    },
    "profile": {
        "intro": "scc profile walkthrough",
        "summary": "Manage multiple named RaaS connections and switch between them.",
        "steps": [
            (
                "1. See what's configured",
                "Shows every saved profile and which one is currently active.",
                "scc profile list",
            ),
            (
                "2. Inspect one without exposing its credential",
                "Server URL, username, and settings only - the password/token never prints.",
                "scc profile show <name>",
            ),
            (
                "3. Store or refresh a credential",
                "Needed after scc connect --no-save, or after a password rotation.",
                "scc profile login <name>",
            ),
            (
                "4. Switch the active default",
                "All following commands use this profile until you switch again or pass --profile.",
                "scc profile use <name>",
            ),
            (
                "5. Use a profile once without switching the default",
                "Handy for a one-off check against a different environment.",
                "scc --profile <name> status",
            ),
            (
                "6. Remove a profile you no longer need",
                "Deletes the saved config and normally forgets its keychain credential too.",
                "scc profile delete <name>",
            ),
        ],
        "next_steps": [
            "Create a new one: `scc tutorial connect`",
            "Move a profile's config between machines without secrets: `scc profile export`",
            "Test all of them at once: `scc profile list` then `scc profile test <name>` for each",
        ],
    },
    "upload": {
        "intro": "scc upload walkthrough",
        "summary": "Push a local file or folder to the RaaS file server.",
        "steps": [
            (
                "1. Upload a single file or a whole folder",
                "Pass either a file or a directory. Folder mode uploads every file inside recursively.",
                "scc upload <local-path>",
            ),
            (
                "2. Know the default remote path",
                "A single file defaults to /<filename>. A folder defaults to "
                "/<folder-name>/... , preserving its internal structure. --path overrides either.",
                "scc upload <local-folder> --path <remote-prefix>",
            ),
            (
                "3. Filter what a folder upload includes",
                "--include/--exclude take fnmatch patterns and can be repeated.",
                'scc upload <local-folder> --include "<pattern>" --exclude "<pattern>"',
            ),
            (
                "4. Preview and confirm before it touches the server",
                "Folder uploads always show the local-to-remote mapping first, then ask for "
                "confirmation - skip the prompt with --yes. --force overwrites existing remote files. "
                "(Dry-run previews belong to state application - see `scc tutorial run`.)",
                "scc upload <local-path> --env <env> --force --yes",
            ),
        ],
        "next_steps": [
            "Run what you just uploaded: `scc run <remote-state> --target-group <group-name> --test`",
            "Browse the file server: `scc fs-list --env <env>`",
            "Full walkthrough for running it: `scc tutorial run`",
        ],
    },
    "run": {
        "intro": "scc run walkthrough",
        "summary": "Execute a state.apply against a target, test-mode by default.",
        "steps": [
            (
                "1. Start in test mode - it is the default",
                "--test/--no-test defaults to --test, a safe dry run. Nothing is "
                "applied until you explicitly pass --no-test.",
                "scc run <remote-state> --target <pattern> --test",
            ),
            (
                "2. Target a group instead of a raw pattern",
                "--target-group <group-name> resolves to whatever minions/pattern that group was created with.",
                "scc run <remote-state> --target-group <group-name> --test",
            ),
            (
                "3. Point at the right environment",
                "--env selects the saltenv the state - and anything it imports, like map.jinja/defaults.yaml - is read from.",
                "scc run <remote-state> --target-group <group-name> --env <env> --test",
            ),
            (
                "4. Apply for real once the dry run looks right",
                "--no-test requires typing a confirmation phrase before anything changes.",
                "scc run <remote-state> --target-group <group-name> --env <env> --no-test",
            ),
            (
                "5. It retries once on a known transient error",
                "Right after an upload, RaaS's fileserver cache can briefly lag and "
                "return 'No matching salt environment'. scc run waits a few seconds "
                "and retries automatically before giving up.",
                "scc run <remote-state> --target-group <group-name> --env <env> --wait <seconds>",
            ),
        ],
        "next_steps": [
            "Run without waiting: `scc run <remote-state> --target-group <group-name> --async` then `scc job-status <jid>`",
            "Turn a one-off run into a reusable job: `scc tutorial job-create`",
            "Get scriptable output: `scc run <remote-state> --target-group <group-name> --test --json`",
        ],
    },
    "target-group-create": {
        "intro": "scc target-group-create walkthrough",
        "summary": "Create a reusable named group of minions to target.",
        "steps": [
            (
                "1. See what target groups already exist",
                "Avoid creating a duplicate - check the existing groups first.",
                "scc target-group-list",
            ),
            (
                "2. Choose a target type",
                "glob/grain/compound/pcre match minions dynamically by pattern. "
                "list pins the group to an explicit set of minion IDs instead - use it "
                "when you want a fixed, reviewable membership rather than a pattern "
                "that could match new minions later.",
                'scc target-group-create <group-name> --target "<minion-id>" --target-type list',
            ),
            (
                "3. Or target dynamically by pattern",
                "For glob/grain/compound/pcre, --target holds the pattern instead of a minion ID.",
                'scc target-group-create <group-name> --target "<pattern>" --target-type <glob|grain|compound|pcre>',
            ),
            (
                "4. Document why the group exists",
                "A short description helps the next person decide whether to reuse it.",
                'scc target-group-create <group-name> --target "<pattern-or-minion-id>" --target-type <type> --description "<description>"',
            ),
            (
                "5. Verify and reuse it",
                "Confirm it saved, then reference it by name from run/exec/job-create instead of repeating raw targets.",
                "scc target-group-list",
            ),
        ],
        "next_steps": [
            "Run a state against it: `scc run <state> --target-group <group-name> --test`",
            "Create a job against it: `scc job-create <job-name> -f <function> --target-group <group-name>`",
            "List groups anytime: `scc target-group-list`",
        ],
    },
    "target-group-list": {
        "intro": "scc target-group-list walkthrough",
        "summary": "See what target groups already exist before creating a new one or picking one to deploy against.",
        "steps": [
            (
                "1. See everything configured",
                "Shows every saved target group with its target pattern/minion list and type.",
                "scc target-group-list",
            ),
            (
                "2. Filter by name",
                "Useful once there are more than a handful of groups.",
                "scc target-group-list --name <pattern>",
            ),
            (
                "3. See pillar associations too",
                "Shows which persistent pillars (from `scc upload-pillar`/`scc pillar-assign`) are tied to each group, not just its targets.",
                "scc target-group-list --show-pillars",
            ),
            (
                "4. Script-friendly output",
                "Same data as machine-readable JSON - useful for picking a group name/UUID in a script rather than parsing the table.",
                "scc target-group-list --json",
            ),
        ],
        "next_steps": [
            "Don't see the right one? Create it: `scc tutorial target-group-create`",
            "Use a group's name directly: `scc deploy <resource> --target-group <group-name> --mode dry-run`",
            "Or with the low-level path: `scc run <state> --target-group <group-name> --test`",
        ],
    },
    "job-create": {
        "intro": "scc job-create walkthrough",
        "summary": "Save a reusable function+target+arguments as a named job.",
        "steps": [
            (
                "1. Understand what a saved job is",
                "A saved job is a reusable, named function + target + arguments, run "
                "repeatedly with `job-run` instead of retyping a full ad-hoc command "
                "every time.",
                "scc job-list",
            ),
            (
                "2. Define the function and target",
                "-f/--function is the Salt function to run. Target it with an existing "
                "target group rather than a raw pattern, so it stays reviewable.",
                "scc job-create <job-name> -f <function> --target-group <group-name>",
            ),
            (
                "3. Pass state.apply arguments the safe way",
                "For state.apply, put the state reference in -a/--arg (positional) and "
                "everything else in --kwarg key=value. Avoid --state/--env here - they "
                "wrap the value in job-input metadata that collides with the positional "
                "argument and breaks the run.",
                "scc job-create <job-name> -f state.apply -a <state-ref> --kwarg saltenv=<env> --target-group <group-name>",
            ),
            (
                "4. Add a description and re-run to update",
                "job-create matches by name - running it again with the same name "
                "updates that job in place instead of creating a duplicate.",
                'scc job-create <job-name> -f <function> -a <state-ref> --kwarg saltenv=<env> --target-group <group-name> --description "<description>"',
            ),
            (
                "5. Verify what actually got saved",
                "Confirm the stored function, target and kwargs match what you intended before anyone runs it.",
                "scc job-list --json",
            ),
        ],
        "next_steps": [
            "Run it: `scc job-run \"<job-name>\"`",
            "Change its behavior later by re-running job-create with the same name.",
            "Inspect stored arguments: `scc job-list --json`",
        ],
    },
    "job-run": {
        "intro": "scc job-run walkthrough",
        "summary": "Execute a previously saved job by name.",
        "steps": [
            (
                "1. Find the job to run",
                "List saved jobs to confirm the exact name before running one.",
                "scc job-list",
            ),
            (
                "2. Understand the safety prompt",
                "Read-only functions (test.ping, grains.*, pillar.get, ...) run "
                "immediately. Anything else - including state.apply - asks you to "
                "type a confirmation phrase first.",
                'scc job-run "<job-name>"',
            ),
            (
                "3. There is no --test/--no-test flag here",
                "Unlike `scc run`, a saved job's dry-run behavior is whatever was "
                "baked in at job-create time via --kwarg test=<True|False>. To change "
                "it, update the job with job-create again rather than passing a flag "
                "to job-run.",
                "scc job-create <job-name> -f <function> -a <state-ref> --kwarg saltenv=<env> --kwarg test=<True|False> --target-group <group-name>",
            ),
            (
                "4. Control how long to wait",
                "--wait <seconds> caps how long to watch for completion (0 = no "
                "timeout). --no-wait submits and returns immediately instead.",
                'scc job-run "<job-name>" --wait <seconds>',
            ),
            (
                "5. Check results anytime, even later",
                "A job's JID keeps working after you've moved on - fetch status or full results whenever you need them.",
                "scc job-status <jid>",
            ),
        ],
        "next_steps": [
            "Fire-and-forget: `scc job-run \"<job-name>\" --no-wait`",
            "Check progress later: `scc job-status <jid>`",
            "Full results: `scc job-results <jid>`",
        ],
    },

}


# The customer-facing Git tutorials intentionally favour the high-level
# workflow. Low-level pull/upload/job commands remain available for operators
# who need individual control, but first-time users should not have to chain
# six commands by hand.
TOPIC_TUTORIALS.update(
    {
        "gitops": {
            "intro": "Git-backed Salt deployment in four simple steps",
            "summary": "Configure two Git sources once, preview the selected content, dry-run it, then apply after Git approval.",
            "steps": [
                (
                    "1. Configure the reusable states and private values sources",
                    "Use one source for open/shared Salt states and another for customer-specific data. "
                    "Repository metadata is stored in repositories.yaml; passwords and tokens stay in Git/SSH credential helpers or the OS keychain.",
                    "scc repo setup",
                ),
                (
                    "2. Build a no-change deployment plan",
                    "SCC fetches the configured refs, resolves the environment/version file, validates the complete state tree and YAML, and displays the exact commits and files. Nothing is sent to RaaS.",
                    "scc deploy <resource> --environment <environment> --version <version>",
                ),
                (
                    "3. Publish and run test=True",
                    "After review, SCC uploads the reusable state tree, passes values.yaml as execution-scoped pillar, submits state.apply directly with test=True, and shows the RaaS JID plus per-target results.",
                    "scc deploy <resource> --environment <environment> --version <version> --mode dry-run --target-group <group>",
                ),
                (
                    "4. Apply after Git approval",
                    "After the customer change is reviewed and merged in Git, SCC pulls the configured refs again, shows the resolved commits, confirms the target group, and applies with test=False.",
                    "scc deploy <resource> --environment <environment> --version <version> --mode apply --target-group <group>",
                ),
            ],
            "next_steps": [
                "See configured sources: `scc repo list`",
                "Validate repository access: `scc repo test --all`",
                "For production, select an approved tag or immutable commit instead of a moving branch",
                "Use persistent RaaS pillar only when explicitly required: add `--values-mode pillar`",
                "Use individual operations when needed: `scc tutorial pull`, `scc tutorial upload`, or `scc tutorial job-create`",
            ],
        },
        "workflow": {
            "intro": "scc deploy walkthrough",
            "summary": "The recommended simple workflow: preview, Git approval, dry-run, and apply.",
            "steps": [
                (
                    "1. One-time source setup",
                    "Define the shared saltext-vcf repository and the private customer-values repository. SCC never stores Git tokens in the RaaS connection profile.",
                    "scc repo setup",
                ),
                (
                    "2. Plan",
                    "A plan syncs both Git refs, validates content, and displays the exact commits and file list. It does not contact RaaS.",
                    "scc deploy <resource> --environment <environment> --version <version>",
                ),
                (
                    "3. Dry-run",
                    "SCC publishes the state files and directly executes state.apply with test=True. values.yaml is passed as runtime pillar and no persistent saved job is created.",
                    "scc deploy <resource> --environment <environment> --version <version> --mode dry-run --target-group <group>",
                ),
                (
                    "4. Git approval and apply",
                    "Use the customer repository's pull-request and branch-protection process for approval. SCC then pulls the current configured refs, displays the exact commits, and requires confirmation before test=False.",
                    "scc deploy <resource> --environment <environment> --version <version> --mode apply --target-group <group>",
                ),
            ],
            "next_steps": [
                "Start with the purpose-built tutorial: `scc tutorial gitops`",
                "Inspect the selected commits and files in the deployment plan output",
                "Show advanced deployment options: `scc help deploy`",
            ],
        },
        "pull": {
            "intro": "scc pull walkthrough",
            "summary": "Copy a complete reusable Salt resource from a named Git source for local review.",
            "steps": [
                (
                    "1. Prefer deploy for the normal journey",
                    "Most users do not need to pull, upload, and execute states separately. scc deploy performs those steps safely and shows provenance.",
                    "scc deploy <resource> --environment <environment> --version <version>",
                ),
                (
                    "2. Use pull when you need a local editable copy",
                    "SCC copies the complete resource directory recursively, including .sls, Jinja templates, defaults, and supporting files—not a hard-coded file list.",
                    "scc pull <resource> --dir ./states",
                ),
                (
                    "3. Select or override the source",
                    "Named sources are configured with scc repo. A one-command URL/ref override is available for investigation without modifying the catalog.",
                    "scc repo list && scc pull <resource> --source vcf-salt",
                ),
                (
                    "4. Publish only after review",
                    "The low-level upload remains available, but scc deploy is recommended because it validates Git content, displays commit provenance, and can continue into a safe direct dry-run.",
                    "scc upload ./states/<resource> --path /<resource> --env <salt-env>",
                ),
            ],
            "next_steps": [
                "Recommended end-to-end path: `scc tutorial gitops`",
                "Inspect source settings: `scc repo show vcf-salt`",
                "Validate access before pulling: `scc repo test vcf-salt`",
            ],
        },
        "pull-data": {
            "intro": "scc pull-data walkthrough",
            "summary": "Resolve one environment/version values file from a private Git source.",
            "steps": [
                (
                    "1. Keep customer data separate",
                    "Reusable Salt states belong in the shared repository. Instance, environment, and version-specific values belong in the customer-controlled repository and can follow its normal pull-request approval process.",
                    "scc repo add customer-values --kind data --url <private-url> --layout '{environment}/{version}/{resource}/values.yaml' --default",
                ),
                (
                    "2. Resolve data by intent, not a long path",
                    "The configured layout maps environment, version, resource, and optional values selectors to the customer file path.",
                    "scc pull-data <resource> --environment prod --version 9.1.1",
                ),
                (
                    "3. Runtime-only is the safe default",
                    "scc deploy injects values.yaml as execution-scoped pillar in the direct state.apply request. It is not uploaded to the file server and no saved job is created. Choose --values-mode pillar only when persistence is explicitly required.",
                    "scc deploy <resource> --environment prod --version 9.1.1 --mode dry-run --target-group <group>",
                ),
                (
                    "4. Git remains the approval system",
                    "Approve and merge customer changes through the repository workflow. SCC shows the resolved values commit and path before apply and requires target confirmation.",
                    "scc deploy <resource> --environment prod --version 9.1.1 --mode apply --target-group <group>",
                ),
            ],
            "next_steps": [
                "Configure layouts interactively: `scc repo setup`",
                "Test the private source: `scc repo test customer-values`",
                "Use an explicit file only when needed: `scc deploy <resource> --values-path <path>`",
            ],
        },
        "repo": {
            "intro": "scc repo walkthrough",
            "summary": "Register the shared states source and the private customer-values source, then verify access.",
            "steps": [
                (
                    "1. Guided setup for both sources",
                    "Prompts for the reusable-state repository (public/shared) and, optionally, a separate customer-values repository (private, per-environment). Tokens are never written to repositories.yaml.",
                    "scc repo setup",
                ),
                (
                    "2. Or add the states source non-interactively",
                    "--root is where resource folders live inside the repo (e.g. vcf-infra). States sources default to layout '{resource}' and normally don't need --layout set.",
                    "scc repo add vcf-salt --kind states --url <url> --root vcf-infra --default",
                ),
                (
                    "3. Add the private customer-values source the same way",
                    "--layout is what makes this a data source - it maps {resource}/{environment}/{version}/{values} to a file path inside the repo.",
                    "scc repo add customer-values --kind data --url <url> --layout '{environment}/{version}/{resource}/values.yaml' --auth token --default",
                ),
                (
                    "4. Store the private source's credentials",
                    "Only needed for --auth token sources. Saved in the OS keychain, never in repositories.yaml. A source-specific env var also works: SCC_GIT_TOKEN_<SOURCE_NAME_UPPER>.",
                    "scc repo login customer-values",
                ),
                (
                    "5. Verify access before deploying anything",
                    "Confirms SCC can actually reach and check out both sources - catches a bad URL, missing token, or wrong branch before scc deploy does.",
                    "scc repo test --all",
                ),
                (
                    "6. Inspect sources later",
                    "Useful once you have more than one states or data source configured (e.g. multiple customer repos). scc repo show <name> and scc repo use <name> work the same way.",
                    "scc repo list",
                ),
            ],
            "next_steps": [
                "Continue with a deployment plan: `scc tutorial deploy`",
                "Full guided path: `scc tutorial gitops`",
                "See every repo subcommand: `scc help repo`",
            ],
        },
        "deploy": {
            "intro": "scc deploy walkthrough",
            "summary": "Understand the four modes and the flags that trip up a first deploy against a real states repo.",
            "steps": [
                (
                    "1. Start with plan - it's read-only",
                    "The default mode. Resolves both Git refs, validates the state tree and values file, and shows exact commits and file list. No RaaS changes, no upload, no execution.",
                    "scc deploy <resource> --environment <environment> --version <version>",
                ),
                (
                    "2. The resource must sit at the right place on the file server",
                    "By default, --remote-path mirrors the states source's Git path (root/resource), and --salt-env defaults to your profile's default_environment. If a resource's .sls/map.jinja use relative imports assuming the resource sits at the environment's *root* (common in flat, single-purpose state repos), the defaults will nest it one level too deep and every render fails with a TemplateNotFound error. If that happens, pin both explicitly:",
                    "scc deploy <resource> --environment <environment> --version <version> --salt-env <env> --remote-path <resource>",
                ),
                (
                    "3. A target group must already exist",
                    "--target-group is required for --mode dry-run and --mode apply, and scc deploy does not create one for you - target groups are a separate, one-time setup step.",
                    "scc target-group-create <name> --target <minion-id-or-pattern> --target-type list",
                ),
                (
                    "4. Dry-run first",
                    "Publishes the state tree and executes state.apply directly with test=True. Doesn't create a persistent job unless --save-job is added.",
                    "scc deploy <resource> --environment <environment> --version <version> --mode dry-run --target-group <group>",
                ),
                (
                    "5. Apply only after Git approval",
                    "Requires typing a confirmation phrase, then executes with test=False. Use the customer repository's pull-request process as the actual approval gate before running this.",
                    "scc deploy <resource> --environment <environment> --version <version> --mode apply --target-group <group>",
                ),
                (
                    "6. A saved job is opt-in and applies for real by default",
                    "--save-job persists a reusable RaaS job pinned to test=False - it will apply for real every time it's run via scc job-run, with no dry-run option through scc deploy itself. Treat creating one with the same care as --mode apply.",
                    "scc deploy <resource> --environment <environment> --version <version> --mode dry-run --target-group <group> --save-job",
                ),
            ],
            "next_steps": [
                "If a resource needs --salt-env/--remote-path every time, that's expected for flat-layout state repos - not a bug to work around once and forget",
                "Full guided path: `scc tutorial gitops`",
                "Every flag: `scc help deploy`",
            ],
        },
    }
)



# Customer-journey tutorials use concrete DNS examples so first-time users can
# understand the end-to-end flow without learning the low-level SCC command set.
TOPIC_TUTORIALS["dns"] = {
    "intro": "Deploy DNS configuration from Git to a RaaS target group",
    "summary": "Add the saltext-vcf and customer-values repositories, preview DNS, run test=True, then apply.",
    "steps": [
        (
            "1. Add the open-source saltext-vcf repository",
            "This repository owns reusable states, default.yaml, map.jinja, and the static KB catalog. "
            "The DNS resource is resolved from vcf-infra/dns. Replace the example URL with your repository URL.",
            "scc repo add vcf-salt --kind states --url https://github.com/your-org/saltext-vcf.git --ref v9.1.1 --root vcf-infra --layout '{resource}' --default",
        ),
        (
            "2. Add the private customer-values repository",
            "Customer-specific settings stay in a separate repository and follow the customer's normal pull-request approval process. "
            "For DNS, SCC resolves prod/9.1.1/dns/values.yaml. Customer values are never uploaded to the RaaS file server.",
            "scc repo add customer-values --kind data --url ssh://git@git.example.com/customer/vcf-config.git --ref main --root . --layout '{environment}/{version}/{resource}/values.yaml' --auth ssh --default",
        ),
        (
            "3. Verify both repositories",
            "SCC authenticates with Git/SSH, fetches the configured refs, and shows the resolved commits. No content is sent to RaaS.",
            "scc repo test --all",
        ),
        (
            "4. Preview the DNS deployment",
            "Plan mode validates vcf-infra/dns/dns.sls, default.yaml, map.jinja, and the selected values.yaml. "
            "It shows the state and values commits and makes no RaaS changes.",
            "scc deploy dns --environment prod --version 9.1.1",
        ),
        (
            "5. Run a safe DNS dry-run",
            "SCC publishes only vcf-infra/dns to the RaaS file server, passes values.yaml as execution-scoped pillar, "
            "submits state.apply directly with test=True, and tracks the returned JID. No persistent saved job is created.",
            "scc deploy dns --environment prod --version 9.1.1 --target-group prod-vcf-components --mode dry-run",
        ),
        (
            "6. Apply after reviewing the dry-run",
            "After the customer values change is approved and merged in Git, SCC refreshes both refs, displays the exact commits and target group, "
            "and asks for confirmation before test=False.",
            "scc deploy dns --environment prod --version 9.1.1 --target-group prod-vcf-components --mode apply",
        ),
    ],
    "next_steps": [
        "Inspect configured sources: `scc repo list`",
        "Review DNS source details: `scc repo show vcf-salt`",
        "See the generic Git workflow: `scc tutorial gitops`",
        "Search for a KB-mapped DNS solution: `scc tutorial kb-search`",
    ],
}


TOPIC_TUTORIALS["kb-search"] = {
    "intro": "Search a KB article and run its reviewed Salt mapping",
    "summary": "Search the static saltext-vcf catalog by KB ID or symptom, inspect the mapping, dry-run it, then apply.",
    "steps": [
        (
            "1. Search by symptom or error text",
            "SCC reads solutions/catalog.yaml from the configured saltext-vcf revision. The catalog is static and Git-reviewed; "
            "SCC and the Config AI Agent never invent a KB-to-SLS mapping.",
            "scc kb search 'DNS lookup failed' --component 'NSX Manager' --version 9.1.1",
        ),
        (
            "2. Search by a known KB number",
            "When the customer already knows the article number, search or show it directly. Replace KB-123456 with the catalog ID returned by search.",
            "scc kb show KB-123456",
        ),
        (
            "3. Review the mapped DNS state",
            "The details show the KB title, supported products/components/versions, verification status, risk, values schema, and the single mapped state such as vcf-infra.dns.dns.",
            "scc kb show KB-123456 --json",
        ),
        (
            "4. Build a no-change resolution plan",
            "SCC verifies that the mapped SLS exists in the same saltext-vcf commit and resolves prod/9.1.1/dns/values.yaml from the private customer repository. Nothing is executed.",
            "scc kb plan KB-123456 --environment prod --version 9.1.1",
        ),
        (
            "5. Execute the mapped solution with test=True",
            "SCC uploads only the reusable DNS state folder, passes customer values as runtime pillar, directly submits state.apply, and tracks the RaaS JID.",
            "scc kb execute KB-123456 --environment prod --version 9.1.1 --target-group prod-vcf-components --mode dry-run",
        ),
        (
            "6. Apply after review",
            "After reviewing the dry-run and confirming the Git-approved values, rerun in apply mode. SCC requires confirmation before test=False.",
            "scc kb execute KB-123456 --environment prod --version 9.1.1 --target-group prod-vcf-components --mode apply",
        ),
    ],
    "next_steps": [
        "Try the fictional bundled examples: `scc kb list --demo`",
        "Demo DNS mapping: `scc kb show DEMO-DNS-001 --demo`",
        "Validate the production catalog: `scc kb validate`",
        "Use JSON for an AI agent or MCP integration: `scc kb search 'DNS mismatch' --json`",
    ],
}


# Keep the shorter historical topic as a generic KB overview while guiding new
# users to the concrete customer journey.
TOPIC_TUTORIALS["kb"] = {
    "intro": "Find and execute a reviewed KB-to-Salt solution",
    "summary": "Understand the static KB catalog, then follow the concrete DNS KB customer journey.",
    "steps": [
        (
            "1. The catalog belongs to saltext-vcf",
            "KB mappings and the resource SLS are versioned together. SCC consumes the catalog; it does not maintain production mappings inside the CLI package.",
            "scc kb validate",
        ),
        (
            "2. Search the static catalog",
            "Search by KB ID, title, symptom, error text, component, or VCF version. Ranking may be dynamic, but the returned mapping is static.",
            "scc kb search 'DNS lookup failed' --component 'NSX Manager' --version 9.1.1",
        ),
        (
            "3. Inspect and plan",
            "Review the single mapped state and build a plan before any RaaS publication or execution.",
            "scc kb show KB-123456 && scc kb plan KB-123456 --environment prod --version 9.1.1",
        ),
        (
            "4. Dry-run before apply",
            "The mapped state executes directly with customer values as runtime pillar and test=True. Apply remains an explicit, confirmed action.",
            "scc kb execute KB-123456 --environment prod --version 9.1.1 --target-group prod-vcf-components --mode dry-run",
        ),
    ],
    "next_steps": [
        "Open the complete example: `scc tutorial kb-search`",
        "See the direct DNS journey: `scc tutorial dns`",
        "Explore fictional examples: `scc kb list --demo`",
        "Agent-friendly JSON: `scc kb search <query> --json`",
    ],
}



def _summary(command: click.Command) -> str:
    return command.get_short_help_str(limit=90) or ""


def _catalog(group: click.Group, ctx: click.Context) -> dict[str, list[tuple[str, str]]]:
    result: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for name in group.list_commands(ctx):
        command = group.get_command(ctx, name)
        if command is None or command.hidden:
            continue
        category = CATEGORY_BY_COMMAND.get(name, "Other")
        result[category].append((name, _summary(command)))
    return result


def register(group: click.Group) -> None:
    @group.command("commands")
    @click.option("--category", type=str, help="Show only one category.")
    @click.pass_context
    def commands_cmd(ctx: click.Context, category: str | None) -> None:
        """List every command with a one-line summary."""
        catalog = _catalog(group, ctx.parent or ctx)
        wanted = category.casefold() if category else None
        if is_plain():
            for category_name, rows in catalog.items():
                if wanted and wanted not in category_name.casefold():
                    continue
                click.echo(f"\n{category_name}:")
                for command_name, description in sorted(rows):
                    click.echo(f"  scc {command_name:<24} {description}")
            return
        for name, rows in catalog.items():
            if wanted and wanted not in name.casefold():
                continue
            table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2), expand=True)
            table.add_column(style="scc.cmd", no_wrap=True)
            table.add_column(style="scc.value", overflow="fold")
            for command_name, description in sorted(rows):
                table.add_row(f"scc {command_name}", description)
            console.print(Panel(table, title=f"[scc.title]{name}[/scc.title]", border_style="scc.primary", box=box.ROUNDED))

    @group.command("search")
    @click.argument("term")
    @click.pass_context
    def search_cmd(ctx: click.Context, term: str) -> None:
        """Find commands by keyword."""
        needle = term.casefold()
        matches: list[tuple[str, str, str]] = []
        catalog = _catalog(group, ctx.parent or ctx)
        for category, rows in catalog.items():
            for name, description in rows:
                command = group.get_command(ctx.parent or ctx, name)
                full = " ".join([name, description, getattr(command, "help", "") or ""])
                if needle in full.casefold():
                    matches.append((name, description, category))
        if not matches:
            if is_plain():
                click.echo(f"No commands matched '{term}'.")
            else:
                console.print(f"[scc.warning]{ICONS['warning']} No commands matched '{term}'.[/scc.warning]")
            next_steps(["Try a broader keyword.", "Run `scc commands` to browse everything."])
            return
        if is_plain():
            click.echo(f"Search results: {term}")
            for name, description, category_name in matches:
                click.echo(f"  scc {name:<24} {description} [{category_name}]")
            return
        table = Table(title=f"Search results: {term}", box=box.ROUNDED, header_style="scc.secondary")
        table.add_column("Command", style="scc.cmd", no_wrap=True)
        table.add_column("Summary", style="scc.value")
        table.add_column("Category", style="scc.hint")
        for name, description, category in matches:
            table.add_row(f"scc {name}", description, category)
        console.print(table)

    @group.command("examples")
    @click.option("--topic", help="Filter recipes by topic.")
    def examples_cmd(topic: str | None) -> None:
        """Show copy-pasteable recipes for common operations."""
        needle = topic.casefold() if topic else None
        shown = 0
        for title, description, commands in EXAMPLES:
            searchable = " ".join([title, description, *commands]).casefold()
            if needle and needle not in searchable:
                continue
            if is_plain():
                click.echo(f"\n{title}")
                click.echo(description)
                for command in commands:
                    click.echo(f"  $ {command}")
            else:
                body = Text(description, style="scc.value")
                body.append("\n\n")
                for command in commands:
                    body.append("$ ", style="scc.muted")
                    body.append(command, style="scc.cmd")
                    body.append("\n")
                console.print(Panel(body, title=f"[scc.title]{title}[/scc.title]", border_style="scc.accent", box=box.ROUNDED))
            shown += 1
        if not shown:
            if is_plain():
                click.echo(f"No examples matched '{topic}'.")
            else:
                console.print(f"[scc.warning]No examples matched '{topic}'.[/scc.warning]")

    @group.command("tutorial")
    @click.argument("topic", required=False)
    @click.option("--non-interactive", is_flag=True, help="Print the walkthrough without prompts.")
    def tutorial_cmd(topic: str | None, non_interactive: bool) -> None:
        """Open a guided SCC walkthrough.

        \b
        Run with no arguments for the five-minute general walkthrough, or
        pass a command name for a walkthrough focused on just that command.

        \b
        Examples:
          $ scc tutorial list
          $ scc tutorial
          $ scc tutorial target-group-create
          $ scc tutorial job-create
          $ scc tutorial job-run
          $ scc tutorial dns
          $ scc tutorial kb-search
        """
        if topic == "list":
            if is_plain():
                click.echo("Available tutorials:")
                click.echo("  (general)               The five-minute end-to-end walkthrough.")
                for name in sorted(TOPIC_TUTORIALS):
                    click.echo(f"  {name:<23} {TOPIC_TUTORIALS[name].get('summary', '')}")
                return
            table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2), expand=True)
            table.add_column(style="scc.cmd", no_wrap=True)
            table.add_column(style="scc.value", overflow="fold")
            table.add_row("(general)", "The five-minute end-to-end walkthrough.")
            for name in sorted(TOPIC_TUTORIALS):
                table.add_row(name, TOPIC_TUTORIALS[name].get("summary", ""))
            console.print(Panel(table, title="[scc.title]Available tutorials[/scc.title]", border_style="scc.primary", box=box.ROUNDED))
            next_steps([
                "Run the general walkthrough: `scc tutorial`",
                "Run a topic walkthrough: `scc tutorial <topic>` (e.g. `scc tutorial job-create`)",
            ])
            return

        if topic:
            topic_data = TOPIC_TUTORIALS.get(topic)
            if topic_data is None:
                if is_plain():
                    click.echo(f"No tutorial for '{topic}'.")
                else:
                    console.print(f"[scc.warning]{ICONS['warning']} No tutorial for '{topic}'.[/scc.warning]")
                next_steps([f"Available topics: {', '.join(sorted(TOPIC_TUTORIALS))}", "Run `scc tutorial` for the general walkthrough."])
                return
            intro = topic_data["intro"]
            steps = topic_data["steps"]
            closing = topic_data["next_steps"]
            closing_title = "You are ready"
        else:
            intro = "Salt Config CLI five-minute guided walkthrough"
            steps = [
                (
                    "1. Connect once",
                    "Create a named RaaS profile and store its credential in the OS keychain—not in YAML.",
                    "scc configure --name lab && scc profile login lab",
                ),
                (
                    "2. Configure Git sources once",
                    "Point SCC at the reusable state repository and the customer-controlled data repository. Git credentials remain in SSH/Git credential helpers, environment variables, or the OS keychain.",
                    "scc repo setup",
                ),
                (
                    "3. Ask for a plan",
                    "Select a resource, environment, and version. SCC syncs both repos, validates the complete content, and shows the exact commits and files. No RaaS changes are made.",
                    "scc deploy <resource> --environment <environment> --version <version>",
                ),
                (
                    "4. Run safely",
                    "Publish the reviewed state tree and execute state.apply directly with test=True plus runtime values against one target group.",
                    "scc deploy <resource> --environment <environment> --version <version> --mode dry-run --target-group <group>",
                ),
                (
                    "5. Apply after repository approval",
                    "After the customer change is approved and merged in Git, SCC pulls the configured refs, displays the exact commits, and confirms the target before allowing test=False.",
                    "scc deploy <resource> --environment <environment> --version <version> --mode apply --target-group <group>",
                ),
            ]
            closing = ["Deploy DNS step by step: `scc tutorial dns`", "Search and execute a KB mapping: `scc tutorial kb-search`", "Use the generic Git workflow: `scc tutorial gitops`"]
            closing_title = "You are ready"

        if is_plain():
            click.echo(intro)
            click.echo("No network calls are made by this tutorial.\n")
            for title, description, command in steps:
                click.echo(title)
                click.echo(textwrap.fill(description, width=96))
                click.echo(f"\n  $ {command}\n")
                if not non_interactive and click.get_text_stream("stdin").isatty():
                    click.prompt("Press Enter for the next step", default="", show_default=False)
        else:
            console.print(Panel(f"[scc.primary]{intro}[/scc.primary]\n[scc.hint]No network calls are made by this tutorial.[/scc.hint]", border_style="scc.primary", box=box.ROUNDED))
            for title, description, command in steps:
                section(title, icon="sparkle")
                console.print(textwrap.fill(description, width=96), style="scc.value")
                console.print(f"\n  [scc.cmd]$ {command}[/scc.cmd]\n")
                if not non_interactive and click.get_text_stream("stdin").isatty():
                    click.prompt("Press Enter for the next step", default="", show_default=False)
        next_steps(closing, title=closing_title)

    @group.command("help")
    @click.argument("command_name", required=False)
    @click.pass_context
    def help_cmd(ctx: click.Context, command_name: str | None) -> None:
        """Show friendly help for one command."""
        if not command_name:
            help_ctx = ctx.parent or ctx
            click.echo(group.get_help(help_ctx), color=help_ctx.color, nl=False)
            return
        command = group.get_command(ctx.parent or ctx, command_name)
        if command is None:
            raise click.ClickException(f"Unknown command: {command_name}")
        command_ctx = click.Context(
            command,
            info_name=command_name,
            parent=ctx.parent,
            color=(ctx.parent or ctx).color,
            terminal_width=(ctx.parent or ctx).terminal_width,
        )
        click.echo(command.get_help(command_ctx), color=command_ctx.color, nl=False)
