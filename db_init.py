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
        value_score REAL,
        novelty_score REAL,
        interest_score REAL,
        embedding BLOB,
        is_high_value BOOLEAN DEFAULT 0,
        user_feedback TEXT,  -- 'positive', 'negative', or NULL
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CHECK (is_high_value IN (0, 1))
    )
    """)

    # Source discovery and tracking (updated with quality management)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS discovered_sources (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT UNIQUE NOT NULL,
        source_type TEXT NOT NULL,  -- 'rss', 'webpage', 'reddit', 'twitter', etc.
        discovery_method TEXT,      -- 'crawl', 'link_follow', 'recommendation'
        parent_url TEXT,           -- URL where this source was discovered
        quality_score REAL DEFAULT 1.0,
        estimated_quality BOOLEAN DEFAULT 1,  -- 1=estimated, 0=actual
        last_quality_update TIMESTAMP,
        last_crawled TIMESTAMP,
        crawl_count INTEGER DEFAULT 0,
        is_active BOOLEAN DEFAULT 1,
        discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CHECK (is_active IN (0, 1))
    )
    """)

    # Learning from user feedback
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS learning_feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id TEXT NOT NULL,
        feedback_type TEXT NOT NULL,  -- 'false_positive', 'false_negative'
        original_score REAL,
        content_features TEXT,        -- JSON of extracted features
        source_features TEXT,         -- JSON of source characteristics
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE
    )
    """)

    # Source reliability tracking (enhanced)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS source_penalties (
        source TEXT PRIMARY KEY,
        penalty_score REAL NOT NULL DEFAULT 1.0,
        value_ratio REAL DEFAULT 0.5,  -- ratio of high-value content
        last_flagged TIMESTAMP,
        total_posts INTEGER DEFAULT 0,
        high_value_posts INTEGER DEFAULT 0,
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

    # Interest profile weights (enhanced for learning) - UPDATED
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS interest_profile (
        category TEXT PRIMARY KEY,
        current_weight REAL NOT NULL,
        learning_adjustment REAL DEFAULT 0.0,
        positive_feedback_count INTEGER DEFAULT 0,
        negative_feedback_count INTEGER DEFAULT 0,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        boost_factor REAL DEFAULT 1.0  -- NEW COLUMN ADDED
    )
    """)

    # Content features for machine learning
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS content_features (
        post_id TEXT PRIMARY KEY,
        word_count INTEGER,
        readability_score REAL,
        technical_terms_count INTEGER,
        source_authority REAL,
        content_depth REAL,
        uniqueness_score REAL,
        FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE
    )
    """)

    # Link discovery tracking
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS link_discovery (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_url TEXT NOT NULL,
        discovered_url TEXT NOT NULL,
        context TEXT,              -- surrounding text where link was found
        discovery_score REAL,      -- potential value score
        explored BOOLEAN DEFAULT 0,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CHECK (explored IN (0, 1))
    )
    """)

    # Initialize interest profile weights from config
    from config import INTEREST_CONFIG
    # Initialize interest profile weights with boost factors
    for category, config in INTEREST_CONFIG["categories"].items():
        # Add boost factor to category config
        config["boost"] = config.get("boost", 1.0)  # Default to 1.0 if not set
        
        cursor.execute("""
        INSERT OR IGNORE INTO interest_profile 
        (category, current_weight, boost_factor)
        VALUES (?, ?, ?)
        """, (category, config["weight"], config["boost"]))

    # Initialize some high-quality seed sources
    seed_sources = [
        ("https://news.ycombinator.com/", "webpage", "seed"),
        ("https://arxiv.org/list/cs.AI/recent", "webpage", "seed"),
        ("https://www.lesswrong.com/", "webpage", "seed"),
        ("https://marginalrevolution.com/", "webpage", "seed"),
        ("https://astralcodexten.substack.com/", "webpage", "seed"),
        ("https://www.stratechery.com/", "webpage", "seed"),
    ]
    
    for url, source_type, method in seed_sources:
        cursor.execute("""
        INSERT OR IGNORE INTO discovered_sources 
        (url, source_type, discovery_method, quality_score)
        VALUES (?, ?, ?, ?)
        """, (url, source_type, method, 1.2))

    # Create indexes for better performance
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_posts_value_score ON posts(value_score)
    """)
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_posts_high_value ON posts(is_high_value)
    """)
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_posts_topic ON posts(topic)
    """)
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_posts_source ON posts(source)
    """)
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_posts_feedback ON posts(user_feedback)
    """)
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_discovered_sources_active ON discovered_sources(is_active)
    """)
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_learning_feedback_type ON learning_feedback(feedback_type)
    """)
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_link_discovery_explored ON link_discovery(explored)
    """)

    conn.commit()
    conn.close()
    print("Database initialization complete - all tables verified/created")

if __name__ == "__main__":
    initialize_database()
    print("Database initialized successfully")
