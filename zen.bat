@echo off
:: zen.bat — Windows shortcut for `zen` CLI
:: Place this in a directory on your PATH, or run `pip install -e .` from the Zen root.
python "%~dp0zen_cli.py" %*
