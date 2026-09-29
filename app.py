"""
app.py — Menu-driven front door for the crypto research tool.

Run:
    python app.py

Provides simple menu access to backtesting, batch testing, and
out-of-sample validation without needing to remember CLI flags.
"""
import os
import subprocess
import sys


# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------
def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def print_header():
    print("=" * 60)
    print("  CRYPTO RESEARCH TOOL — TECHNICAL SIGNALS")
    print("=" * 60)
    print()


def print_menu():
    print("  1. Run single backtest (one strategy, one pair)")
    print("  2. Run batch test (many pairs × timeframes)")
    print("  3. Run out-of-sample validation")
    print("  4. List available strategies")
    print("  5. Show past results")
    print("  6. Exit")
    print()


def prompt(msg, default=None):
    if default is not None:
        msg = f"{msg} [{default}]: "
    else:
        msg = f"{msg}: "
    val = input(msg).strip()
    if not val and default is not None:
        return default
    return val


def run_command(cmd: list):
    """Run a subprocess and wait."""
    print()
    print(f"  > {' '.join(cmd)}")
    print()
    try:
        subprocess.run(cmd, check=False)
    except KeyboardInterrupt:
        print("\n[INFO] Interrupted.")
    print()
    input("Press Enter to return to the menu...")


# ---------------------------------------------------------------
# Menu actions
# ---------------------------------------------------------------
def action_single_backtest():
    clear_screen()
    print_header()
    print("  SINGLE BACKTEST\n")

    strategy = prompt("Strategy name (e.g. breakout)")
    pair = prompt("Pair (e.g. SOL/USDT)", default="SOL/USDT")
    timeframe = prompt("Timeframe (5m, 15m, 1h, 4h)", default="1h")
    days = prompt("Days of data", default="180")

    cmd = [sys.executable, "cli.py", "run",
           "--pair", pair,
           "--strategy", strategy,
           "--timeframe", timeframe,
           "--days", days]
    run_command(cmd)


def action_batch():
    clear_screen()
    print_header()
    print("  BATCH TEST\n")
    print("  Default: 5 top pairs × 5m,1h\n")

    strategy = prompt("Strategy name (e.g. breakout)")
    pairs = prompt("Pairs (comma-separated, blank for default)",
                   default="SOL/USDT,BTC/USDT,ETH/USDT,BNB/USDT,XRP/USDT")
    timeframes = prompt("Timeframes (comma-separated)",
                        default="5m,1h")

    cmd = [sys.executable, "batch.py",
           "--strategy", strategy,
           "--pairs", pairs,
           "--timeframes", timeframes]
    run_command(cmd)


def action_oos():
    clear_screen()
    print_header()
    print("  OUT-OF-SAMPLE VALIDATION\n")
    print("  Default: 5 pairs, 1h, 180 days ending 2026-03-31\n")

    strategy = prompt("Strategy name (e.g. breakout)")
    end_date = prompt("End date (YYYY-MM-DD)", default="2026-03-31")
    pair_choice = prompt("Pairs (blank for default 5)", default="")

    cmd = [sys.executable, "oos_test.py",
           "--strategy", strategy,
           "--end-date", end_date]
    if pair_choice:
        cmd += ["--pairs", pair_choice]
    run_command(cmd)


def action_list_strategies():
    clear_screen()
    print_header()
    print("  AVAILABLE STRATEGIES\n")

    try:
        import registry
        names = registry.list_strategies()
        for name in names:
            try:
                desc = registry.describe_strategy(name)
                params = ", ".join(f"{k}={v}"
                                   for k, v in desc["params"].items())
                print(f"  {name:12s}  {desc['description']}")
                print(f"               params: {params}")
                print()
            except Exception as e:
                print(f"  {name:12s}  (error: {e})")
    except Exception as e:
        print(f"  [ERROR] Could not load registry: {e}")

    print()
    input("Press Enter to return to the menu...")


def action_show_results():
    clear_screen()
    print_header()
    print("  PAST RESULTS\n")

    results_dirs = ["research/batch_results", "."]
    csvs = []
    for d in results_dirs:
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.endswith(".csv") and f.startswith(("batch_", "oos_",
                                                        "grid_")):
                    csvs.append(os.path.join(d, f))

    if not csvs:
        print("  No results found.")
        print("  (Run a batch or OOS test first.)")
        print()
        input("Press Enter to return to the menu...")
        return

    print("  Found results:\n")
    for i, path in enumerate(sorted(csvs), 1):
        size = os.path.getsize(path)
        print(f"  {i}. {path}  ({size} bytes)")

    print()
    choice = prompt(f"Open which one? (1-{len(csvs)}, blank to skip)",
                    default="")
    if choice:
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(csvs):
                target = sorted(csvs)[idx]
                print(f"\n  --- {target} ---\n")
                with open(target, "r") as f:
                    print(f.read())
        except Exception as e:
            print(f"  [ERROR] {e}")

    print()
    input("Press Enter to return to the menu...")


# ---------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------
def main():
    # Sanity check we're in the right folder
    required = ["cli.py", "batch.py", "oos_test.py", "config.py"]
    missing = [f for f in required if not os.path.exists(f)]
    if missing:
        print(f"[ERROR] Missing files: {missing}")
        print("Run this script from the project root folder.")
        sys.exit(1)

    while True:
        clear_screen()
        print_header()
        print_menu()

        choice = prompt("Choose [1-6]", default="6")

        if choice == "1":
            action_single_backtest()
        elif choice == "2":
            action_batch()
        elif choice == "3":
            action_oos()
        elif choice == "4":
            action_list_strategies()
        elif choice == "5":
            action_show_results()
        elif choice == "6":
            print("\n  Goodbye.\n")
            return
        else:
            print("\n  Invalid choice. Try again.")
            input("Press Enter to continue...")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Interrupted. Goodbye.\n")