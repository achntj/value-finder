import streamlit as st
import sqlite3

DATABASE = "database.db"

def load_posts():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT title, content, url FROM posts ORDER BY created_at DESC")
    posts = cursor.fetchall()
    conn.close()
    return posts

st.title("Your Daily Digest")

posts = load_posts()

for title, content, url in posts:
    st.header(title)
    st.write(content)
    st.markdown(f"[Read more]({url})", unsafe_allow_html=True)

