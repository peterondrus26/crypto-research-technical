"""
app.py — Menu-driven front door for the crypto research tool.

Run:
    python app.py
"""
import os
import subprocess
import sys
from datetime import datetime


# ---------------------------------------------------------------
# Preset shortcuts
# ---------------------------------------------------------------
COMMON_PAIRS = [
    "SOL/USDT",
    "BTC/USDT",
    "ETH/USDT",
    "BNB/USDT",
    "XRP/USDT",
]

PAIRS_URL = "https://www.binance.com/en/markets"

DEFAULT_STRATEGY = "breakout"

LOG_DIR = os.path.join("research", "logs")


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


def _build_log_filename(prefix: str, *parts) -> str:
    """
    Build a log filename like:
      backtest_breakout_SOLUSDT_1h_20260929_161234.txt
    """
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_parts = []
    for p in parts:
        safe = str(p).replace("/", "").replace(" ", "").replace(",", "-")
        if safe:
            safe_parts.append(safe)
    middle = "_".join(safe_parts) if safe_parts else "run"
    return f"{prefix}_{middle}_{stamp}.txt"


def open_in_default_viewer(path: str):
    """Open the file in the OS default viewer (Notepad on Windows)."""
    try:
        if os.name == "nt":
            os.startfile(path)   # noqa: S606 (Windows-specific)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        print(f"  [WARN] Could not auto-open: {e}")


def run_command(cmd, log_prefix: str, log_parts=None, auto_open=True):
    """
    Run a subprocess, stream its output to the terminal AND to a log file.
    On completion, print the log path and optionally open it.

    log_parts: list of strings used to build the log filename.
    """
    os.makedirs(LOG_DIR, exist_ok=True)
    log_name = _build_log_filename(log_prefix, *(log_parts or []))
    log_path = os.path.join(LOG_DIR, log_name)

    print()
    print(f"  > {' '.join(cmd)}")
    print(f"  [INFO] Saving output to: {log_path}")
    print()

    header = (
        "=" * 70 + "\n"
        f"  COMMAND: {' '.join(cmd)}\n"
        f"  STARTED: {datetime.now().isoformat()}\n"
        + "=" * 70 + "\n\n"
    )

    exit_code = 0
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(header)
            f.flush()

            # Run process, capture combined stdout/stderr
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )

            for line in proc.stdout:
                # Print live to terminal
                print(line, end="")
                # Save to log
                f.write(line)
                f.flush()

            proc.wait()
            exit_code = proc.returncode
            f.write("\n\n" + "=" * 70 + "\n")
            f.write(f"  EXIT CODE: {exit_code}\n")
            f.write(f"  FINISHED:  {datetime.now().isoformat()}\n")
            f.write("=" * 70 + "\n")

    except KeyboardInterrupt:
        print("\n[INFO] Interrupted.")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("\n[INTERRUPTED BY USER]\n")
    except Exception as e:
        print(f"\n[ERROR] {e}")

    print()
    print(f"  [INFO] Result saved to: {log_path}")

    if auto_open:
        print("  [INFO] Opening in default viewer...")
        open_in_default_viewer(log_path)

    print()
    input("Press Enter to return to the menu...")


# ---------------------------------------------------------------
# Strategy / pair selectors
# ---------------------------------------------------------------
def _load_strategies():
    try:
        import registry
        out = []
        for name in registry.list_strategies():
            try:
                info = registry.describe_strategy(name)
                out.append((name, info.get("description", "")))
            except Exception:
                out.append((name, ""))
        return out
    except Exception:
        return []


def pick_strategy(default: str = DEFAULT_STRATEGY) -> str:
    strategies = _load_strategies()

    if strategies:
        print("  Available strategies:")
        for i, (name, desc) in enumerate(strategies, 1):
            print(f"    {i}. {name:12s}  {desc}")
        print()

    choice = prompt("Choose strategy (name or number)", default=default)

    if choice.isdigit():
        idx = int(choice) - 1
        if strategies and 0 <= idx < len(strategies):
            return strategies[idx][0]
    return choice


def pick_pair(default: str = "SOL/USDT") -> str:
    print("  Common pairs:")
    for i, p in enumerate(COMMON_PAIRS, 1):
        print(f"    {i}. {p}")
    print(f"\n  Full list of pairs: {PAIRS_URL}")
    print()

    choice = prompt("Choose pair (number, name, or Enter for default)",
                    default=default)

    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(COMMON_PAIRS):
            return COMMON_PAIRS[idx]

    return choice


def pick_timeframe(default: str = "1h") -> str:
    options = ["5m", "15m", "1h", "4h", "1d"]
    print("  Timeframes:")
    print("    1. 5m    2. 15m    3. 1h    4. 4h    5. 1d")
    print()

    choice = prompt("Choose timeframe (number or value)", default=default)

    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(options):
            return options[idx]

    return choice


# ---------------------------------------------------------------
# Menu actions
# ---------------------------------------------------------------
def action_single_backtest():
    clear_screen()
    print_header()
    print("  SINGLE BACKTEST\n")

    strategy = pick_strategy()
    print()
    pair = pick_pair()
    print()
    timeframe = pick_timeframe()
    print()
    days = prompt("Days of data", default="180")

    cmd = [sys.executable, "cli.py", "run",
           "--pair", pair,
           "--strategy", strategy,
           "--timeframe", timeframe,
           "--days", days]

    log_parts = [strategy, pair, timeframe, f"{days}d"]
    run_command(cmd, log_prefix="backtest", log_parts=log_parts)


def action_batch():
    clear_screen()
    print_header()
    print("  BATCH TEST\n")

    strategy = pick_strategy()
    print()

    print("  Pairs (comma-separated names, or 'default' for top 5):")
    print(f"    Common: {', '.join(COMMON_PAIRS)}")
    print(f"    Full list: {PAIRS_URL}")
    print()
    pairs = prompt("Pairs",
                   default="SOL/USDT,BTC/USDT,ETH/USDT,BNB/USDT,XRP/USDT")
    print()

    print("  Timeframes (comma-separated): 5m,15m,1h,4h,1d")
    timeframes = prompt("Timeframes", default="5m,1h")

    cmd = [sys.executable, "batch.py",
           "--strategy", strategy,
           "--pairs", pairs,
           "--timeframes", timeframes]

    # Trim pair list for filename readability
    n_pairs = len(pairs.split(","))
    log_parts = [strategy, f"{n_pairs}pairs", timeframes.replace(",", "-")]
    run_command(cmd, log_prefix="batch", log_parts=log_parts)


def action_oos():
    clear_screen()
    print_header()
    print("  OUT-OF-SAMPLE VALIDATION\n")

    strategy = pick_strategy()
    print()
    end_date = prompt("End date (YYYY-MM-DD)", default="2026-03-31")
    print()
    print("  Pairs (blank for default top 5):")
    print(f"    Default: {', '.join(COMMON_PAIRS)}")
    print()
    pair_choice = prompt("Pairs", default="")

    cmd = [sys.executable, "oos_test.py",
           "--strategy", strategy,
           "--end-date", end_date]
    if pair_choice:
        cmd += ["--pairs", pair_choice]

    log_parts = [strategy, end_date]
    run_command(cmd, log_prefix="oos", log_parts=log_parts)


def action_list_strategies():
    clear_screen()
    print_header()
    print("  AVAILABLE STRATEGIES\n")

    strategies = _load_strategies()

    if not strategies:
        print("  [ERROR] Could not load registry.")
    else:
        for name, desc in strategies:
            try:
                import registry
                info = registry.describe_strategy(name)
                params = ", ".join(f"{k}={v}"
                                   for k, v in info["params"].items())
                print(f"  {name:12s}  {desc}")
                print(f"               params: {params}")
                print()
            except Exception as e:
                print(f"  {name:12s}  (error: {e})")

    print(f"  Full pair list: {PAIRS_URL}")
    print()
    input("Press Enter to return to the menu...")


def action_show_results():
    clear_screen()
    print_header()
    print("  PAST RESULTS\n")

    # Search both CSV results and TXT logs
    search = [
        ("CSV results", "research/batch_results", (".csv",),
         ("batch_", "oos_", "grid_")),
        ("TXT logs", LOG_DIR, (".txt",), ("backtest_", "batch_", "oos_")),
    ]

    all_files = []
    for label, folder, exts, prefixes in search:
        if not os.path.isdir(folder):
            continue
        for f in sorted(os.listdir(folder)):
            if any(f.endswith(e) for e in exts) and \
                    any(f.startswith(p) for p in prefixes):
                all_files.append(os.path.join(folder, f))

    if not all_files:
        print("  No results found.")
        print("  (Run a batch or OOS test first.)")
        print()
        input("Press Enter to return to the menu...")
        return

    print("  Found results (newest first):\n")
    all_files.sort(key=os.path.getmtime, reverse=True)
    for i, path in enumerate(all_files, 1):
        size = os.path.getsize(path)
        mtime = datetime.fromtimestamp(os.path.getmtime(path))
        stamp = mtime.strftime("%Y-%m-%d %H:%M")
        print(f"  {i:2d}. [{stamp}]  {path}  ({size} bytes)")

    print()
    choice = prompt(f"Open which one? (1-{len(all_files)}, blank to skip)",
                    default="")
    if choice:
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(all_files):
                target = all_files[idx]
                print(f"\n  Opening: {target}")
                open_in_default_viewer(target)
        except Exception as e:
            print(f"  [ERROR] {e}")

    print()
    input("Press Enter to return to the menu...")


# ---------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------
def main():
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