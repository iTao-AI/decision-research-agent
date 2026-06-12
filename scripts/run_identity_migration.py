"""Apply and verify the additive run identity migration."""
import argparse
import json
from pathlib import Path
import sys

project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from api.run_migrations import migrate_with_backup


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--backup", required=True)
    args = parser.parse_args()
    result = migrate_with_backup(db_path=args.db, backup_path=args.backup)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
