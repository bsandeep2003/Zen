"""
setup.py — Install Zen as a global CLI tool.

After running `pip install -e .` from the Zen root:
  - `zen fix "python main.py"` works from anywhere
  - `zen proceed` re-runs the last failed command
  - `zen status` shows project memory
"""
from setuptools import setup, find_packages

setup(
    name="zen-agent",
    version="1.0.0",
    description="Zen — Autonomous Debugging Agent CLI",
    author="Zen Team",
    py_modules=["zen_cli"],
    install_requires=[
        "httpx>=0.27.0",
    ],
    entry_points={
        "console_scripts": [
            "zen=zen_cli:main",
        ],
    },
)
