import sqlite3

conn = sqlite3.connect("database.db")
cursor = conn.cursor()

# Add a new column to store summaries
cursor.execute("ALTER TABLE posts ADD COLUMN summary TEXT")

conn.commit()
conn.close()

print("Summary column added to posts table.")
