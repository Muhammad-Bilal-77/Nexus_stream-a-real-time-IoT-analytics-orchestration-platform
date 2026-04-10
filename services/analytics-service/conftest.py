"""
conftest.py — Shared pytest fixtures for analytics-service tests.

Sets PYTHONPATH so that `from app.xxx import ...` works from the tests/ folder.
"""
import sys
import os

# Add the service root to PYTHONPATH so imports resolve correctly
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
