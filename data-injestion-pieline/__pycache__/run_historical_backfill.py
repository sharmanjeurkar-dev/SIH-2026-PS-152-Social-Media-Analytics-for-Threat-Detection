
"""
Historical Backfill Automation Runner for Member 1
SIH 2026 PS:152 - National Technical Research Organisation (NTRO)

ONE-COMMAND EXECUTION:
    python3 run_backfill.py

Iterates month-by-month from Jan 2026 to current date, executing main.py in deep-history mode.
Pushes all records to Kafka ('raw-threat-stream') and partitioned storage.
Includes an automated circuit breaker (kill switch) triggered after >2 consecutive failed chunks.
"""

import sys
import time
import argparse
import subprocess
import logging
from datetime import datetime, date, timezone
import calendar

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Default: Start from January 1, 2026 through current date
START_DATE = date(2026, 1, 1)
COOLDOWN_BETWEEN_CHUNKS_SECS = 5.0
MAX_CONSECUTIVE_FAILURES = 2  # Triggers kill switch when failures exceed this threshold


def generate_monthly_slices(start_date: date, end_date: date):
    """Generates sequential (start_date, end_date) tuples covering each month."""
    slices = []
    current_start = start_date

    while current_start < end_date:
        _, last_day_of_month = calendar.monthrange(current_start.year, current_start.month)
        month_end = date(current_start.year, current_start.month, last_day_of_month)
        current_end = min(month_end, end_date)

        slices.append((current_start.strftime("%Y-%m-%d"), current_end.strftime("%Y-%m-%d")))

        if current_end.month == 12:
            current_start = date(current_end.year + 1, 1, 1)
        else:
            current_start = date(current_end.year, current_end.month + 1, 1)

    return slices


def run_backfill(start_date: date = START_DATE, end_date: date = None, target: str = None, no_fallback: bool = False):
    today = end_date or datetime.now(timezone.utc).date()
    date_slices = generate_monthly_slices(start_date, today)

    logging.info("=" * 75)
    logging.info("  NTRO HISTORICAL INGESTION RUNNER - PS:152")
    logging.info("  [MEMBER 1] Full Historical Scraping & Kafka Ingestion")
    logging.info(f"  Target Range: {start_date} -> {today}")
    logging.info(f"  Total Monthly Chunks to Process: {len(date_slices)}")
    logging.info(f"  Kafka Destination Topic: 'raw-threat-stream'")
    logging.info(f"  Circuit Breaker: Auto-kill after >{MAX_CONSECUTIVE_FAILURES} consecutive failures")
    if target:
        logging.info(f"  Filter Single Target: {target}")
    logging.info("=" * 75)

    consecutive_failures = 0
    last_successful_chunk = None
    successful_chunks = []

    for idx, (start_str, end_str) in enumerate(date_slices, start=1):
        chunk_label = f"Chunk {idx}/{len(date_slices)} [{start_str} to {end_str}]"
        logging.info(f"\n[*] Starting {chunk_label}...")

        cmd = [
            sys.executable,
            "main.py",
            "--mode",
            "deep-history",
            "--start-date",
            start_str,
            "--end-date",
            end_str,
        ]
        if target:
            cmd.extend(["--target", target])
        if no_fallback:
            cmd.append("--no-fallback")

        try:
            subprocess.run(cmd, check=True)
            logging.info(f"[✓] {chunk_label} completed successfully.")

            # Reset consecutive failure counter on success
            consecutive_failures = 0
            last_successful_chunk = (start_str, end_str)
            successful_chunks.append(chunk_label)

        except subprocess.CalledProcessError as e:
            consecutive_failures += 1
            logging.error(f"[✗] {chunk_label} failed with exit code {e.returncode}.")
            logging.warning(f"[!] Consecutive failure count: {consecutive_failures}/{MAX_CONSECUTIVE_FAILURES + 1}")

            # Circuit breaker kill switch trigger
            if consecutive_failures > MAX_CONSECUTIVE_FAILURES:
                print("\n" + "!" * 75)
                print("  [KILL SWITCH TRIGGERED] More than 2 consecutive chunks failed.")
                print(f"  Failed attempting chunk: {chunk_label}")
                if last_successful_chunk:
                    print(f"  Last successful chunk range: {last_successful_chunk[0]} to {last_successful_chunk[1]}")
                    print(f"  Total successful chunks completed: {len(successful_chunks)} of {len(date_slices)}")
                    print("  Completed chunks summary:")
                    for sc in successful_chunks:
                        print(f"    - {sc}")
                else:
                    print("  No chunks were successfully completed before failure threshold was reached.")
                print("  Probable Cause: Hard IP ban or rate limit across target endpoints.")
                print("  Recommended Action: Switch VPN server/proxy IP and resume from the failed date range.")
                print("!" * 75 + "\n")
                sys.exit(1)

            logging.warning("[!] Pausing 15s before attempting next chunk...")
            time.sleep(15.0)

        except KeyboardInterrupt:
            logging.info("\n[*] Backfill runner interrupted by user. Stopping gracefully...")
            if last_successful_chunk:
                print(f"[*] Last successful chunk before interrupt: {last_successful_chunk[0]} to {last_successful_chunk[1]}")
            sys.exit(0)

        # Standard cooldown between chunks
        if idx < len(date_slices) and consecutive_failures == 0:
            logging.info(f"[*] Sleeping {COOLDOWN_BETWEEN_CHUNKS_SECS}s before next chunk...\n")
            time.sleep(COOLDOWN_BETWEEN_CHUNKS_SECS)

    print("\n" + "=" * 75)
    print("  [✓] BACKFILL COMPLETE")
    print(f"  All {len(date_slices)} historical chunks processed successfully.")
    print(f"  Full coverage span: {start_date} to {today}")
    print("=" * 75)


def main():
    parser = argparse.ArgumentParser(description="Member 1: One-Command Historical Backfill Automation Runner")
    parser.add_argument("--start-date", type=str, default=str(START_DATE), help="Start date (YYYY-MM-DD), default: 2026-01-01")
    parser.add_argument("--end-date", type=str, help="End date (YYYY-MM-DD), default: today")
    parser.add_argument("--target", type=str, help="Filter on a single hashtag or topic")
    parser.add_argument("--no-fallback", action="store_true", help="Disable synthetic fallback (real HTTP only)")

    args = parser.parse_args()

    s_dt = datetime.strptime(args.start_date, "%Y-%m-%d").date()
    e_dt = datetime.strptime(args.end_date, "%Y-%m-%d").date() if args.end_date else None

    run_backfill(start_date=s_dt, end_date=e_dt, target=args.target, no_fallback=args.no_fallback)


if __name__ == "__main__":
    main()