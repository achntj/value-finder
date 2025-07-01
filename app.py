import sqlite3
import streamlit as st

DATABASE = "database.db"

def get_top_posts(limit=20):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT title, content, url, score 
        FROM posts 
        WHERE content IS NOT NULL AND score IS NOT NULL
        ORDER BY score DESC
        LIMIT ?
    """, (limit,))
    posts = cursor.fetchall()
    conn.close()
    return posts

def app():
    st.title("Your Daily Digest")

    posts = get_top_posts()

    for idx, (title, content, url, score) in enumerate(posts):
        st.markdown(f"### [{title}]({url})  ")
        st.write(content)
        st.caption(f"Score: {score:.3f}")
        st.markdown("---")

if __name__ == "__main__":
    app()

