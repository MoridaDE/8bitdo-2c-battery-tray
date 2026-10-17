#!/usr/bin/env python3
"""CLI status for 8BitDo Ultimate 2C battery tray."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backend import EightBitDo2CBackend, EstimateStore  # noqa: E402

CONFIG = os.path.expanduser("~/.config/8bitdo-2c-battery")


def main() -> None:
    hw = EightBitDo2CBackend().read()
    est = EstimateStore(os.path.join(CONFIG, "estimate"), 18.0)
    print(
        json.dumps(
            {**hw.__dict__, "estimate": int(round(est.percentage))},
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
