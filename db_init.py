# db_init.py
import sqlite3
from datetime import datetime

def initialize_database():
    """Initialize all database tables with proper schema if they don't exist"""
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    # Enable foreign key constraints
    cursor.execute("PRAGMA foreign_keys = ON")

    # Posts table (main content storage)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS posts (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        url TEXT NOT NULL,
        content TEXT,
        summary TEXT,
        source TEXT NOT NULL,
        topic TEXT,
        score REAL,
        embedding BLOB,
        is_favorite BOOLEAN DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CHECK (is_favorite IN (0, 1))
    )
    """)

    # Flagged content tracking
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS flagged_content (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id TEXT NOT NULL,
        reason TEXT NOT NULL,
        severity INTEGER NOT NULL DEFAULT 1,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE,
        CHECK (severity BETWEEN 1 AND 3)
    )
    """)

    # Source reliability tracking
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS source_penalties (
        source TEXT PRIMARY KEY,
        penalty_score REAL NOT NULL DEFAULT 1.0,
        last_flagged TIMESTAMP,
        CHECK (penalty_score BETWEEN 0.0 AND 1.0)
    )
    """)

    # Scheduler state tracking
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scheduler_state (
        task_name TEXT PRIMARY KEY,
        last_run TIMESTAMP NOT NULL
    )
    """)

    # User feedback storage
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id TEXT NOT NULL,
        quality INTEGER,
        relevance INTEGER,
        notes TEXT,
        rating_type TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE
    )
    """)

    # Interest profile weights
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS interest_profile (
        category TEXT PRIMARY KEY,
        current_weight REAL NOT NULL,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Initialize interest profile weights from config
    from config import INTEREST_CONFIG
    for category, config in INTEREST_CONFIG["categories"].items():
        cursor.execute("""
        INSERT OR IGNORE INTO interest_profile 
        (category, current_weight)
        VALUES (?, ?)
        """, (category, config["weight"]))

    # Create indexes for better performance
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_posts_score ON posts(score)
    """)
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_posts_topic ON posts(topic)
    """)
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_posts_source ON posts(source)
    """)
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_posts_favorite ON posts(is_favorite)
    """)
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_flagged_content_post ON flagged_content(post_id)
    """)

    conn.commit()
    conn.close()
    print("Database initialization complete - all tables verified/created")

if __name__ == "__main__":
    initialize_database()
    print("Database initialized successfully")
