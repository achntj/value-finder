import sqlite3
import requests

DATABASE = "database.db"
OLLAMA_MODEL = "llama3"
OLLAMA_URL = "http://localhost:11434/api/generate"

def summarize_with_ollama(text):
    if not text or len(text.strip()) < 30:
        return ""

    prompt = f"Summarize this post for someone interested in AI, productivity, writing, philosophy, and tech startups:\n\n{text.strip()}"

    response = requests.post(OLLAMA_URL, json={
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False
    })

    try:
        return response.json()["response"].strip()
    except:
        return ""

def process_posts():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, content FROM posts WHERE content IS NOT NULL AND content != ''")
    rows = cursor.fetchall()

    for post_id, content in rows:
        summary = summarize_with_ollama(content)
        if summary:
            cursor.execute("UPDATE posts SET content = ? WHERE id = ?", (summary, post_id))
            conn.commit()

    conn.close()

if __name__ == "__main__":
    process_posts()

