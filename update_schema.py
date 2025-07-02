# update_schema.py
import sqlite3


def update_database_schema():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    # Create main posts table if not exists
    cursor.execute(
        """
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
            created_at TIMESTAMP,
            last_updated TIMESTAMP
        )
    """
    )

    # Create feedback table
    cursor.execute(
        """
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
    """
    )

    # Create interest profile table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS interest_profile (
            category TEXT PRIMARY KEY,
            current_weight REAL,
            last_updated TIMESTAMP
        )
    """
    )

    # Create source reliability table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS source_reliability (
            source TEXT PRIMARY KEY,
            reliability_score REAL,
            last_updated TIMESTAMP
        )
    """
    )

    # Add any missing columns to posts table
    try:
        cursor.execute("ALTER TABLE posts ADD COLUMN embedding BLOB")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()
    print("✅ Database schema updated successfully.")


if __name__ == "__main__":
    update_database_schema()
