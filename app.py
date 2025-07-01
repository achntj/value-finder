# app.py
import streamlit as st
import sqlite3

st.set_page_config(page_title="WebScout", layout="centered")
st.title("Your Smart Daily Digest")

conn = sqlite3.connect("database.db")
cursor = conn.cursor()
cursor.execute(
    "SELECT title, url, summary, score, source FROM posts WHERE score IS NOT NULL ORDER BY score DESC LIMIT 20"
)
posts = cursor.fetchall()

for title, url, summary, score, source in posts:
    st.markdown(f"### [{title}]({url})")
    st.markdown(f"**Source:** {source} | **Score:** {score:.2f}")
    st.markdown(summary)
    st.markdown("---")
