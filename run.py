#!/usr/bin/env python3
"""
Fidelity Alpha Tracker — Interactive Launcher
Walks you through import → analysis in one script.
"""

import subprocess
import sys
from pathlib import Path

DATA_DIR = Path("data")

CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def ask(prompt, default="y"):
    """Ask a yes/no question."""
    suffix = " [Y/n] " if default == "y" else " [y/N] "
    answer = input(f"{CYAN}{prompt}{RESET}{suffix}").strip().lower()
    if not answer:
        return default == "y"
    return answer in ("y", "yes")


def choose(prompt, options):
    """Display numbered options and return the chosen value."""
    print(f"\n{BOLD}{prompt}{RESET}")
    for i, (label, _) in enumerate(options, 1):
        print(f"  {CYAN}{i}{RESET}) {label}")
    while True:
        choice = input(f"\n{CYAN}Enter choice [1-{len(options)}]: {RESET}").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return options[int(choice) - 1]
        print(f"  {YELLOW}Invalid — pick 1-{len(options)}{RESET}")


def main():
    print(f"\n{BOLD}{'═' * 50}{RESET}")
    print(f"{BOLD}  Fidelity Alpha Tracker{RESET}")
    print(f"{BOLD}{'═' * 50}{RESET}\n")

    # Step 1: Import
    csv_count = len(list(DATA_DIR.glob("*.csv"))) if DATA_DIR.exists() else 0
    print(f"{DIM}  Current data/ has {csv_count} CSV file(s){RESET}")

    if ask("Import new CSVs from ~/Downloads?"):
        result = subprocess.run([sys.executable, "import_csv.py"])
        if result.returncode != 0:
            print(f"{YELLOW}  Import had issues — continuing anyway{RESET}")
        print()
    else:
        print(f"{DIM}  Skipping import{RESET}\n")

    csv_count = len(list(DATA_DIR.glob("*.csv"))) if DATA_DIR.exists() else 0
    if csv_count == 0:
        print(f"{YELLOW}No CSV files in data/. Download from Fidelity first.{RESET}")
        return

    # Step 2: Choose mode
    label, mode = choose("How do you want to view results?", [
        ("Dashboard  — interactive browser UI with charts & filtering", "dashboard"),
        ("CLI Report — terminal output + HTML file saved to reports/", "cli"),
        ("Both       — run CLI report, then open dashboard", "both"),
    ])

    print()

    if mode in ("cli", "both"):
        print(f"{GREEN}▶ Running CLI report...{RESET}\n")
        subprocess.run([sys.executable, "main.py"])
        print()

    if mode in ("dashboard", "both"):
        print(f"{GREEN}▶ Starting dashboard at http://localhost:8501{RESET}")
        print(f"{DIM}  Press Ctrl+C to stop{RESET}\n")
        try:
            subprocess.run([sys.executable, "-m", "streamlit", "run", "dashboard.py",
                            "--server.headless", "true"])
        except KeyboardInterrupt:
            print(f"\n{DIM}Dashboard stopped.{RESET}")


if __name__ == "__main__":
    main()
