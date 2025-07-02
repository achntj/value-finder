# update_schema.py
import sqlite3
from datetime import datetime
from config import INTEREST_CONFIG

def update_database_schema():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    
    # Main posts table with favorite flag
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id TEXT PRIMARY KEY,
            title TEXT,
            url TEXT,
            content TEXT,
            summary TEXT,
            source TEXT,
            topic TEXT,
            score REAL,
            embedding BLOB,
            is_favorite BOOLEAN DEFAULT 0,
            created_at TIMESTAMP,
            last_updated TIMESTAMP
        )
    """)
    
    # Feedback table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id TEXT,
            relevance INTEGER,
            quality INTEGER,
            novelty INTEGER,
            notes TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(post_id) REFERENCES posts(id)
        )
    """)
    
    # Interest profile
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS interest_profile (
            category TEXT PRIMARY KEY,
            current_weight REAL,
            last_updated TIMESTAMP
        )
    """)
    
    # Source reliability
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS source_reliability (
            source TEXT PRIMARY KEY,
            reliability_score REAL,
            last_updated TIMESTAMP
        )
    """)
    
    # Scheduler state
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scheduler_state (
            task_name TEXT PRIMARY KEY,
            last_run TIMESTAMP
        )
    """)
    
    # Initialize interest weights
    for category, config in INTEREST_CONFIG["categories"].items():
        cursor.execute("""
            INSERT OR IGNORE INTO interest_profile 
            (category, current_weight, last_updated)
            VALUES (?, ?, ?)
        """, (category, config["weight"], datetime.now().isoformat()))
    
    conn.commit()
    conn.close()
    print("✅ Database schema updated successfully.")

if __name__ == "__main__":
    update_database_schema()
