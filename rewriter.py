#!/usr/bin/env python3
"""
Backwards-compatible entrypoint.

The implementation has moved into the `oai_to_circuit` package for better
modularity and testability. This file remains so existing docs and commands
(`python rewriter.py ...`) keep working unchanged.
"""

from oai_to_circuit.server import main


if __name__ == "__main__":
    main()
