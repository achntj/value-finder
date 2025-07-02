# scheduler.py
import time
from datetime import datetime, timedelta
import subprocess
import sqlite3
import signal
import sys
from config import INTEREST_CONFIG


class TaskScheduler:
    def __init__(self):
        self.running = True
        signal.signal(signal.SIGINT, self.handle_interrupt)
        signal.signal(signal.SIGTERM, self.handle_interrupt)

    def handle_interrupt(self, signum, frame):
        print("\nReceived shutdown signal, finishing current task...")
        self.running = False

    def get_last_run_time(self, task_name):
        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS scheduler_state (
                task_name TEXT PRIMARY KEY,
                last_run TIMESTAMP
            )
        """
        )
        cursor.execute(
            "SELECT last_run FROM scheduler_state WHERE task_name = ?", (task_name,)
        )
        result = cursor.fetchone()
        conn.close()
        print(result)
        return datetime.fromisoformat(result[0]) if result else None

    def update_last_run_time(self, task_name):
        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO scheduler_state (task_name, last_run)
            VALUES (?, ?)
        """,
            (task_name, datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()

    def should_run_task(self, task_name, interval_hours):
        last_run = self.get_last_run_time(task_name)
        if not last_run:
            return True
        return (datetime.now() - last_run) >= timedelta(hours=interval_hours)

    def run_task(self, command, task_name, interval_hours):
        if not self.should_run_task(task_name, interval_hours):
            print(f"Skipping {task_name}, not due yet")
            return

        print(f"Running {task_name}...")
        try:
            subprocess.run(command, check=True)
            self.update_last_run_time(task_name)
        except subprocess.CalledProcessError as e:
            print(f"Error running {task_name}: {e}")

    def run(self):
        print("Starting WebScout scheduler...")
        while self.running:
            now = datetime.now()
            print(f"\n=== Scheduler cycle at {now} ===")

            # Crawler - run hourly
            self.run_task(["python", "crawler.py"], "crawler", 1)

            # Scorer - run after crawler completes
            self.run_task(["python", "scorer.py"], "scorer", 1)

            # Summarizer - run in batches
            self.run_task(["python", "llm_summarizer.py"], "summarizer", 1)

            # Embedding index - run daily at 3 AM
            if now.hour == 3:
                self.run_task(["python", "embedding.py"], "embedding", 24)

            print("Tasks completed. Waiting for next cycle...")

            # Wait in smaller intervals to be more responsive to signals
            for _ in range(60):  # Check every minute
                if not self.running:
                    break
                time.sleep(60)


if __name__ == "__main__":
    scheduler = TaskScheduler()
    scheduler.run()
    print("Scheduler shutdown complete.")
