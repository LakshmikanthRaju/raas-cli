# Contributing

Thank you for improving Salt Config CLI.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e '.[dev]'
pytest -q
ruff check .
python scripts/check_release.py
```

## Design expectations

- Keep the normal path simple: source setup, plan, dry-run, approval, apply.
- Put reusable behavior in typed core/service modules; Click handlers should coordinate validation, UX, and services.
- Preserve existing command names and machine-readable output where practical.
- Keep RaaS connection profiles and Git source metadata separate.
- Never store secrets in YAML, URLs, manifests, examples, tests, or logs.
- Reuse the system Git client, SSH agent, and credential helpers rather than implementing provider-specific token URLs.
- Default mutation workflows to a no-change plan or `test=True`.
- Add a regression test for every safety boundary and reported failure.
- Keep tutorials network-free and written for a first-time user.

## Pull requests

Include:

- the user problem and intended workflow;
- compatibility/safety impact;
- tests executed;
- sanitized screenshots for UX changes when useful;
- documentation updates for new commands or configuration.

Do not submit customer repositories, internal hostnames, credentials, tokens, production configuration, or proprietary Salt content.
