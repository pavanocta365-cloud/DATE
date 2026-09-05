#!/usr/bin/env python3
"""Nearby - entry point.

Usage:
    python3 run.py [run|seed|reset|check] [--host H] [--port P]

Normally invoked for you by CMake:  cmake -P CMakeLists.txt
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> int:
    parser = argparse.ArgumentParser(prog="nearby")
    parser.add_argument("action", nargs="?", default="run",
                        choices=["run", "seed", "reset", "check"])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    from app import config, db, seed, server

    if args.action == "reset":
        if config.DB_PATH.exists():
            config.DB_PATH.unlink()
        for suffix in ("-wal", "-shm"):
            sidecar = config.DB_PATH.with_name(config.DB_PATH.name + suffix)
            if sidecar.exists():
                sidecar.unlink()
        print("Nearby: database wiped.")

    db.init_db()
    created = seed.seed_if_empty()
    if args.action == "seed":
        print("Nearby: database ready at %s" % config.DB_PATH)
        return 0

    if args.action == "check":
        from app import selftest
        return selftest.run()

    if created:
        print("Nearby: seeded %d demo profiles." % created)

    server.serve(args.host, args.port)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nNearby: stopped.")
        sys.exit(0)
