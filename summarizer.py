# summarizer.py
import sqlite3
import requests

DATABASE = "database.db"


def summarize(text):
    prompt = f"Summarize the following in 3-5 bullet points:\n\n{text}"
    res = requests.post(
        "http://localhost:11434/api/generate",
        json={"model": "llama3", "prompt": prompt, "stream": False},
    )
    return res.json()["response"].strip()


def summarize_unsummarized():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, content FROM posts WHERE summary IS NULL AND content IS NOT NULL"
    )
    rows = cursor.fetchall()

    for post_id, content in rows:
        if len(content.strip()) < 100:
            continue  # skips super short posts
        print(f"Summarizing post {post_id}...")
        try:
            summary = summarize(content[:3000])
            cursor.execute(
                "UPDATE posts SET summary = ? WHERE id = ?", (summary, post_id)
            )
            conn.commit()
        except Exception as e:
            print(f"Failed to summarize {post_id}: {e}")

    conn.close()


if __name__ == "__main__":
    summarize_unsummarized()
