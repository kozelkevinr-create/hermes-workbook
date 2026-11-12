# hermes-workbook

A [Hermes Agent](https://github.com/NousResearch/hermes-agent) plugin that lets agents manage
workbooks, with a **global** scope shared by all profiles and a **per-profile** scope.

> **Status: scaffold.** Plugin contract, tooling and CI are in place. The first slice is
> local `.xlsx`/`.csv` via openpyxl; Google Sheets comes later. See
> [docs/design/mvp.md](docs/design/mvp.md).

## Development

```sh
python3 -m venv .venv && . .venv/bin/activate
python -m pip install -e ".[dev]"
make check
```

## Installing into Hermes

```sh
hermes plugins install <owner>/hermes-workbook --enable
hermes plugins validate .
```

Requires `openpyxl` (declared in `pyproject.toml`; Hermes asks consent and installs it with the
plugin, or run `hermes pm repair`). Without it, xlsx tools return a clear error; csv still works.

Plugin state lives in the Hermes plugin data directories (per profile or global), never in
the install directory. Workbook files live on the machine that runs Hermes.

## Layout

```text
plugin.yaml  __init__.py  hermes_workbook/ (plugin.py, plugin_storage.py, cli.py)
tests/unit  scripts/check_manifest.py  docs/  CLAUDE.md
```

## Branch workflow

`feature/* -> test -> stage -> main`; see [CLAUDE.md](CLAUDE.md).

## License

MIT.
