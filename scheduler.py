# scheduler.py (updated)
import sqlite3
import time
from datetime import datetime, timedelta
import subprocess
import signal
import sys
import logging
from config import INTEREST_CONFIG

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

SOURCE_REHABILITATION_INTERVAL = 7  # days
REHABILITATION_RATE = 1.1  # 10% score increase per cycle
SOURCE_PENALTY_THRESHOLD = 0.6  # Must match other files
PIPELINE_INTERVAL_HOURS = 1  # New constant for pipeline interval


class TaskScheduler:
    def __init__(self):
        self.running = True
        signal.signal(signal.SIGINT, self.handle_interrupt)
        signal.signal(signal.SIGTERM, self.handle_interrupt)
        self.conn = sqlite3.connect("database.db")

    def handle_interrupt(self, signum, frame):
        logger.info("\nReceived shutdown signal")
        self.running = False
        self.conn.close()

    def clean_low_value_content(self):
        """Clean up low-value content without feedback"""
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                DELETE FROM posts 
                WHERE is_high_value = 0 
                AND user_feedback IS NULL 
                AND value_score < 0.3
            """)
            deleted = cursor.rowcount
            self.conn.commit()
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} low-value posts")
            return True
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
            self.conn.rollback()
            return False

    def should_run_task(self, task_name, interval_minutes):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT last_run FROM scheduler_state 
            WHERE task_name = ?
        """,
            (task_name,),
        )
        result = cursor.fetchone()

        if not result:
            return True

        last_run = datetime.fromisoformat(result[0])
        return (datetime.now() - last_run) >= timedelta(minutes=interval_minutes)

    def update_last_run(self, task_name):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO scheduler_state 
            (task_name, last_run)
            VALUES (?, ?)
        """,
            (task_name, datetime.now().isoformat()),
        )
        self.conn.commit()

    def run_task(self, command, task_name, interval_minutes):
        if not self.should_run_task(task_name, interval_minutes):
            logger.info(f"Skipping {task_name} - not due yet")
            return False

        logger.info(f"Running {task_name}...")
        try:
            subprocess.run(command, check=True)
            self.update_last_run(task_name)
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Task {task_name} failed: {e}")
            return False

    def run_pipeline(self):
        """Run the full processing pipeline"""
        if not self.running:
            return False

        # Run standard tasks
        tasks = [
            (["python", "crawler.py"], "crawler", 60),
            (["python", "scorer.py"], "scorer", 60),
            (["python", "llm_summarizer.py"], "summarizer", 60),
        ]

        ran_any = False
        for command, name, interval in tasks:
            if self.run_task(command, name, interval):
                ran_any = True

        return ran_any

    def run(self):
        logger.info("Starting scheduler")

        while self.running:
            try:
                # Run daily maintenance at 3 AM
                if datetime.now().hour == 3:
                    self.clean_low_value_content()
                    self.run_task(
                        ["python", "embedding.py"], "embedding", 1440  # 24 hours
                    )

                # Run main pipeline every {interval} hours
                if self.should_run_task("full_pipeline", PIPELINE_INTERVAL_HOURS * 60):
                    if self.run_pipeline():
                        self.update_last_run("full_pipeline")

                # Check every minute if we should run anything
                for _ in range(60):
                    if not self.running:
                        break
                    time.sleep(1)

            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                time.sleep(60)


if __name__ == "__main__":
    scheduler = TaskScheduler()
    scheduler.run()
    logger.info("Scheduler stopped")
