# llm_summarizer.py
import sqlite3
import requests
import time
import hashlib
from datetime import datetime

DATABASE = "database.db"
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3"
MAX_TOKENS = 3000
SUMMARY_CACHE = {}  # In-memory cache to avoid reprocessing

def get_content_hash(content):
    """Generate consistent hash for content"""
    return hashlib.md5(content.encode()).hexdigest()

def summarize(text):
    """Summarize text with caching"""
    content_hash = get_content_hash(text)

    # Check cache first
    if content_hash in SUMMARY_CACHE:
        return SUMMARY_CACHE[content_hash]

    trimmed = text[:MAX_TOKENS]
    prompt = f"Summarize this in 3–5 clear bullet points, focusing on novel insights and practical value:\n\n{trimmed}"

    try:
        res = requests.post(
            OLLAMA_URL, json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}
        )
        res.raise_for_status()
        summary = res.json()["response"].strip()
        SUMMARY_CACHE[content_hash] = summary  # Cache result
        return summary
    except Exception as e:
        print(f"❌ Error summarizing: {e}")
        return None

def summarize_high_value():
    """Summarize high-value content only"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, content 
        FROM posts 
        WHERE summary IS NULL 
        AND is_high_value = 1
        AND content IS NOT NULL
        ORDER BY value_score DESC
        LIMIT 10
    """
    )
    rows = cursor.fetchall()

    print(f"📝 Summarizing {len(rows)} high-value posts...")

    for idx, (post_id, content) in enumerate(rows):
        print(f"[{idx+1}/{len(rows)}] Summarizing post: {post_id}")
        summary = summarize(content)
        if summary:
            cursor.execute(
                """
                UPDATE posts 
                SET summary = ?, last_updated = ?
                WHERE id = ?
            """,
                (summary, datetime.now(), post_id),
            )
            conn.commit()
        time.sleep(0.3)  # Small pause to avoid hammering Ollama

    conn.close()
    print("✅ High-value summarization complete.")

if __name__ == "__main__":
    summarize_high_value()
