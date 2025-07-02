# app.py
import streamlit as st
import sqlite3
from datetime import datetime
import numpy as np
from config import INTEREST_CONFIG, FEEDBACK_OPTIONS

st.set_page_config(page_title="WebScout", layout="centered", page_icon="🔍")
st.title("Your Smart Daily Digest")

# Initialize database connection
conn = sqlite3.connect("database.db")

# Debug function to check database state
def debug_database():
    cursor = conn.cursor()
    
    # Check if posts table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='posts'")
    if not cursor.fetchone():
        st.error("Posts table doesn't exist in the database!")
        return False
    
    # Count total posts
    cursor.execute("SELECT COUNT(*) FROM posts")
    total_posts = cursor.fetchone()[0]
    st.sidebar.write(f"Total posts in DB: {total_posts}")
    
    # Count scored posts
    cursor.execute("SELECT COUNT(*) FROM posts WHERE score IS NOT NULL")
    scored_posts = cursor.fetchone()[0]
    st.sidebar.write(f"Scored posts: {scored_posts}")
    
    return True

# Sidebar filters and debug info
st.sidebar.header("Filters")
if not debug_database():
    st.stop()

# Get available topics from actual data
cursor = conn.cursor()
cursor.execute("SELECT DISTINCT topic FROM posts WHERE topic IS NOT NULL")
available_topics = [row[0] for row in cursor.fetchall()] or [
    config["name"] for config in INTEREST_CONFIG["categories"].values()
]

selected_categories = st.sidebar.multiselect(
    "Categories",
    options=available_topics,
    default=available_topics[:3] if available_topics else []
)

min_score = st.sidebar.slider("Minimum Score", 0.0, 1.0, 0.0)  # Start at 0 to see all
sources = st.sidebar.multiselect(
    "Sources",
    options=list(INTEREST_CONFIG["source_weights"].keys()),
    default=list(INTEREST_CONFIG["source_weights"].keys())
)

# Main content
tab1, tab2 = st.tabs(["Recommendations", "Debug Info"])

with tab1:
    try:
        # Build the query dynamically based on filters
        query = """
            SELECT id, title, url, summary, score, source, topic 
            FROM posts 
            WHERE score >= ?
        """
        params = [min_score]
        
        # Add source filter if any sources selected
        if sources:
            query += " AND source IN (" + ",".join(["?"] * len(sources)) + ")"
            params.extend(sources)
        
        # Add topic filter if any topics selected
        if selected_categories:
            query += " AND topic IN (" + ",".join(["?"] * len(selected_categories)) + ")"
            params.extend(selected_categories)
        
        query += " ORDER BY score DESC LIMIT 50"
        
        cursor.execute(query, params)
        posts = cursor.fetchall()

        if not posts:
            st.warning("No posts match your current filters. Try:")
            st.markdown("- Lowering the minimum score")
            st.markdown("- Expanding the source selection")
            st.markdown("- Checking if any posts exist in the database")
            
            # Show sample of what's in the DB
            cursor.execute("SELECT title, score, source, topic FROM posts ORDER BY RANDOM() LIMIT 5")
            sample = cursor.fetchall()
            if sample:
                st.write("Sample of posts in database:")
                for title, score, source, topic in sample:
                    st.write(f"{title[:50]}... (Score: {score or 'NULL'}, Source: {source}, Topic: {topic or 'NULL'})")
        else:
            for post_id, title, url, summary, score, source, topic in posts:
                with st.expander(f"{title} ({score:.2f})"):
                    st.markdown(f"**Source:** {source} | **Topic:** {topic}")
                    st.markdown(f"**Summary:** {summary}")
                    st.markdown(f"[Read more]({url})")
                    
                    with st.form(key=f"feedback_{post_id}"):
                        st.write("How was this recommendation?")
                        relevance = st.radio(
                            "Relevance",
                            options=FEEDBACK_OPTIONS["relevance"],
                            key=f"rel_{post_id}"
                        )
                        quality = st.radio(
                            "Quality",
                            options=FEEDBACK_OPTIONS["quality"],
                            key=f"qual_{post_id}"
                        )
                        novelty = st.radio(
                            "Novelty",
                            options=FEEDBACK_OPTIONS["novelty"],
                            key=f"nov_{post_id}"
                        )
                        notes = st.text_area("Additional notes", key=f"notes_{post_id}")
                        
                        if st.form_submit_button("Submit Feedback"):
                            rel_score = FEEDBACK_OPTIONS["relevance"].index(relevance)
                            qual_score = FEEDBACK_OPTIONS["quality"].index(quality)
                            nov_score = FEEDBACK_OPTIONS["novelty"].index(novelty)
                            
                            cursor.execute("""
                                INSERT INTO feedback 
                                (post_id, relevance, quality, novelty, notes)
                                VALUES (?, ?, ?, ?, ?)
                            """, (post_id, rel_score, qual_score, nov_score, notes))
                            conn.commit()
                            st.success("Thanks for your feedback!")
    except sqlite3.Error as e:
        st.error(f"Database error: {e}")

with tab2:
    st.header("Database Debug Information")
    
    # Show schema
    st.subheader("Database Schema")
    cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")
    for table_name, table_sql in cursor.fetchall():
        st.code(f"{table_name}:\n{table_sql}", language="sql")
    
    # Show some sample data
    st.subheader("Sample Posts")
    cursor.execute("""
        SELECT id, title, score, source, topic, summary IS NOT NULL as has_summary
        FROM posts
        ORDER BY RANDOM()
        LIMIT 10
    """)
    sample_data = cursor.fetchall()
    
    if sample_data:
        for post in sample_data:
            st.write(f"**{post[1][:50]}...** (ID: {post[0]})")
            st.write(f"Score: {post[2] or 'NULL'} | Source: {post[3]} | Topic: {post[4] or 'NULL'} | Summary: {'✅' if post[5] else '❌'}")
    else:
        st.warning("No posts found in the database!")

conn.close()
