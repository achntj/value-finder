# scheduler.py
import time
from datetime import datetime
import subprocess
import sqlite3
from config import INTEREST_CONFIG


def run_scheduled_tasks():
    """Run all tasks on a schedule"""
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    while True:
        now = datetime.now()
        print(f"\n=== Running tasks at {now} ===")

        # Check last crawl time
        cursor.execute("SELECT MAX(created_at) FROM posts")
        last_crawl = cursor.fetchone()[0]

        # Crawl every hour
        if (
            not last_crawl
            or (now - datetime.strptime(last_crawl, "%Y-%m-%d %H:%M:%S.%f")).seconds
            > 3600
        ):
            print("Running crawler...")
            subprocess.run(["python", "crawler.py"])

        # Score new content immediately after crawling
        print("Running scorer...")
        subprocess.run(["python", "scorer.py"])

        # Summarize in batches
        print("Running summarizer...")
        subprocess.run(["python", "llm_summarizer.py"])

        # Build embedding index daily
        if now.hour == 3:  # 3 AM
            print("Building embedding index...")
            subprocess.run(["python", "embedding.py"])

        print("Tasks completed. Waiting for next cycle...")
        time.sleep(3600)  # Wait 1 hour


if __name__ == "__main__":
    run_scheduled_tasks()
