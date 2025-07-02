# scheduler.py
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
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
        
    def should_run_task(self, task_name, interval_minutes):
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT last_run FROM scheduler_state 
            WHERE task_name = ?
        """, (task_name,))
        result = cursor.fetchone()
        
        if not result:
            return True
            
        last_run = datetime.fromisoformat(result[0])
        return (datetime.now() - last_run) >= timedelta(minutes=interval_minutes)
        
    def update_last_run(self, task_name):
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO scheduler_state 
            (task_name, last_run)
            VALUES (?, ?)
        """, (task_name, datetime.now().isoformat()))
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
            return
            
        # Check if any task in pipeline needs to run
        tasks = [
            (["python", "crawler.py"], "crawler", 60),
            (["python", "scorer.py"], "scorer", 60),
            (["python", "llm_summarizer.py"], "summarizer", 60)
        ]
        
        ran_any = False
        for command, name, interval in tasks:
            if self.run_task(command, name, interval):
                ran_any = True
                
        return ran_any
        
    def run(self):
        logger.info("Starting WebScout scheduler")
        
        while self.running:
            try:
                # Run the pipeline if needed
                self.run_pipeline()
                
                # Daily tasks
                if datetime.now().hour == 3:  # 3 AM
                    self.run_task(
                        ["python", "embedding.py"], 
                        "embedding", 
                        1440  # 24 hours
                    )
                
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
