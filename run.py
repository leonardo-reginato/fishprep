from __future__ import annotations

import argparse

from fishprep.pipeline import run_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the fishprep image preprocessing pipeline.")
    parser.add_argument(
        "--config",
        default="config.yml",
        help="Path to a YAML configuration file.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_pipeline(args.config)
