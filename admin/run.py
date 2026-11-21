#!/usr/bin/env python3
"""Start Selo Admin: python3 admin/run.py  (settings: see app/config.py; no packages to install)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import web  # noqa: E402

if __name__ == '__main__':
    web.serve()
