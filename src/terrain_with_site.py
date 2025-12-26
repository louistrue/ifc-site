#!/usr/bin/env python3
"""
Legacy compatibility module - redirects to site_model.py

This file is kept for backward compatibility. New code should import from site_model.py directly.
"""

# Import and re-export the main workflow function
from src.site_model import run_combined_terrain_workflow

__all__ = ['run_combined_terrain_workflow']
