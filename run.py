#!/usr/bin/env python3
"""
Development runner script for Salt Config CLI.

Usage:
    python run.py init
    python run.py plan
    python run.py apply
    python run.py --help

Or make executable:
    chmod +x run.py
    ./run.py init
"""

import sys
import os

# Add the project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from salt_config_cli.cli.main import main

if __name__ == "__main__":
    main()
