#!/usr/bin/env python3
"""Compute and print event topic0 hashes for both registries from the vendored ABIs.

topic0 = keccak256(canonical event signature). This script exists so the pinned hashes in
the codebase are demonstrably COMPUTED from the official ABIs (proposal §3.1), never
hand-transcribed. Run:  python scripts/print_topics.py
"""

from __future__ import annotations

from provenalt_indexer import events, reputation


def main() -> None:
    print("Identity Registry", events.IDENTITY_REGISTRY_ADDRESS)
    for name, topic0 in events.TOPIC0.items():
        print(f"  {name:<16} {topic0}")

    print("Reputation Registry", reputation.REPUTATION_REGISTRY_ADDRESS)
    for name, topic0 in reputation.TOPIC0.items():
        print(f"  {name:<16} {topic0}")


if __name__ == "__main__":
    main()
