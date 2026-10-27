"""ClinicalTrail — hackathon entry point.

Usage:
    python run.py                        # runs the built-in demo query
    python run.py --query "your question"
    python run.py --mock                 # offline / mock data
    python run.py --json                 # machine-readable JSON output

This thin wrapper satisfies the hackathon requirement for a `run.py` entry
point.  All logic lives in main.py; this file simply delegates to it.
"""
import sys
from main import main

if __name__ == "__main__":
    sys.exit(main())
