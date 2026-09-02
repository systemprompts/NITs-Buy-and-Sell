"""Quick Supabase Postgres connectivity check.

Usage:
    python scripts/check_db.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text  # noqa: E402

from config import Config  # noqa: E402

url = Config.SQLALCHEMY_DATABASE_URI
safe = url.split("@")[-1] if "@" in url else url
print(f"Connecting to: {safe}")

engine = create_engine(url, **getattr(Config, "SQLALCHEMY_ENGINE_OPTIONS", {}))

try:
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version()")).scalar()
    print("Connection successful!")
    print(version)
except Exception as exc:  # noqa: BLE001
    print(f"Failed to connect: {exc}")
    sys.exit(1)
