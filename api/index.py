"""Vercel serverless entrypoint.

Vercel's @vercel/python runtime detects the module-level ``app`` WSGI callable
and serves it. All routes are rewritten to this function in vercel.json.
"""

import os
import sys

# Make the project root importable when bundled as a serverless function.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402

app = create_app()
