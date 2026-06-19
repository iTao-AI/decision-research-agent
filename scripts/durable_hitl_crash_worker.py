from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time


project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from scripts.durable_hitl_fixture import run_stage


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True)
    parser.add_argument("--marker", required=True)
    parser.add_argument("--root", required=True)
    args = parser.parse_args()

    def stage_hook(stage, workflow):
        if stage == args.stage:
            Path(args.marker).write_text(
                workflow.workflow_id,
                encoding="utf-8",
            )
            while True:
                time.sleep(1)

    run_stage(Path(args.root), args.stage, stage_hook)


if __name__ == "__main__":
    main()
