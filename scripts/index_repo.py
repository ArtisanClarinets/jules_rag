import argparse
import logging
import sys
import os

# Add root to path
sys.path.append(os.getcwd())

from code_intelligence.db import Database
from code_intelligence.indexing import FileIndexer
from code_intelligence.config import settings

logging.basicConfig(level=logging.INFO)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, help="Repo root path")
    parser.add_argument("--repo-id", default="default", help="Repo ID")
    parser.add_argument("--mode", choices=["full", "incremental"], default="incremental")
    parser.add_argument("--force", action="store_true", help="Force re-indexing")

    args = parser.parse_args()

    force = args.force or (args.mode == "full")

    print(f"Indexing {args.root} (mode={args.mode})...")

    db = Database(settings.db_path)
    indexer = FileIndexer(db)

    try:
        stats = indexer.index_workspace(args.root, force=force)
        print(f"Indexing complete: {stats}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
