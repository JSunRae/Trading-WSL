# Config Editor (PyQt)

Minimal GUI to view, validate, diff, and save configuration files under `config/`.

Usage:

- Run via console script: `config-editor`
- Or: `python -m src.ui.config_editor.app`

Features:

- File selector (config.json, ib_gateway_config.json, symbol_mapping.json)
- JSON editing with inline schema validation
- Diff against current file
- Atomic save with timestamped backup

Planned:

- Secrets handling via keyring/Fernet
- Hot reload event broadcast
- Profile support (dev/paper/prod)
