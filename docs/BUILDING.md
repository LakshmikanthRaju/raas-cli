# Building

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
pytest -q
python -m build
python scripts/check_release.py
```

Artifacts are written to `dist/`.
