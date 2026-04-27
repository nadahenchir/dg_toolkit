"""
Standalone script to seed kb_chunks from action_library.
Run once at project launch, and again whenever action_library content changes.

Usage (from project root):
    python -m app.seed.seed_kb
"""
import logging
import sys
import os

# Ensure project root is on the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)

from app.services.layer3.seeder import seed_kb_from_action_library

if __name__ == "__main__":
    print("Starting kb_chunks seeding from action_library...")
    result = seed_kb_from_action_library()
    print(f"\nDone. Inserted: {result['inserted']} | Skipped (already exist): {result['skipped']}")