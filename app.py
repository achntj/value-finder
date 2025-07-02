# app.py
import streamlit as st
import sqlite3
from datetime import datetime
import subprocess
import time
from config import INTEREST_CONFIG, FEEDBACK_OPTIONS
import migrations

# Category mapping
CATEGORY_MAP = {
    config["name"]: category
    for category, config in INTEREST_CONFIG["categories"].items()
}


def get_db_connection():
    conn = sqlite3.connect("database.db")
    try:
        conn.execute("SELECT is_favorite FROM posts LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE posts ADD COLUMN is_favorite BOOLEAN DEFAULT 0")
        conn.commit()
    return conn


def debug_database(conn):
    """Debug database state and return status"""
    cursor = conn.cursor()
    debug_info = {"status": True, "messages": [], "stats": {}}

    try:
        # Check if posts table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='posts'"
        )
        if not cursor.fetchone():
            debug_info["status"] = False
            debug_info["messages"].append("Posts table doesn't exist in the database!")
            return debug_info

        # Get database stats
        cursor.execute("SELECT COUNT(*) FROM posts")
        debug_info["stats"]["total_posts"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM posts WHERE score IS NOT NULL")
        debug_info["stats"]["scored_posts"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM posts WHERE is_favorite = 1")
        debug_info["stats"]["favorite_posts"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM feedback")
        debug_info["stats"]["feedback_entries"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT source) FROM posts")
        debug_info["stats"]["unique_sources"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT topic) FROM posts")
        debug_info["stats"]["unique_topics"] = cursor.fetchone()[0]

        debug_info["messages"].append("Database checks completed successfully")

    except Exception as e:
        debug_info["status"] = False
        debug_info["messages"].append(f"Database error: {str(e)}")

    return debug_info


def run_pipeline():
    with st.spinner("Running full processing pipeline..."):
        subprocess.run(["python", "crawler.py"])
        subprocess.run(["python", "scorer.py"])
        subprocess.run(["python", "llm_summarizer.py"])
        st.success("Pipeline completed successfully!")
        time.sleep(1)
        st.rerun()


def reset_scheduler():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM scheduler_state")
    conn.commit()
    conn.close()
    st.success("Scheduler reset - next run will process immediately")


def cleanup_database():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM posts WHERE is_favorite = 0")
    cursor.execute("DELETE FROM feedback")
    cursor.execute("DELETE FROM interest_profile")

    for category, config in INTEREST_CONFIG["categories"].items():
        cursor.execute(
            """
            INSERT OR REPLACE INTO interest_profile 
            (category, current_weight, last_updated)
            VALUES (?, ?, ?)
        """,
            (category, config["weight"], datetime.now().isoformat()),
        )

    conn.commit()
    conn.close()
    st.success("Database cleaned up - only favorites kept")
    time.sleep(1)
    st.rerun()


def main():
    st.set_page_config(page_title="WebScout", layout="centered", page_icon="🔍")
    st.title("Your Smart Daily Digest")

    conn = get_db_connection()
    debug_info = debug_database(conn)

    with st.sidebar:
        st.header("Controls")
        if st.button("🔄 Run Pipeline Now"):
            run_pipeline()
        if st.button("⏱️ Reset Scheduler"):
            reset_scheduler()
        if st.button("🧹 Cleanup Database"):
            cleanup_database()

        # Debug Info Section
        st.header("Database Status")
        if not debug_info["status"]:
            st.error("Database issues detected!")
            for msg in debug_info["messages"]:
                st.error(msg)
        else:
            st.success("Database healthy")
            cols = st.columns(2)
            cols[0].metric("Total Posts", debug_info["stats"]["total_posts"])
            cols[1].metric("Scored Posts", debug_info["stats"]["scored_posts"])
            cols[0].metric("Favorites", debug_info["stats"]["favorite_posts"])
            cols[1].metric("Feedback Entries", debug_info["stats"]["feedback_entries"])
            st.caption(
                f"Sources: {debug_info['stats']['unique_sources']} | Topics: {debug_info['stats']['unique_topics']}"
            )

        # Filters Section
        st.header("Filters")
        selected_categories = st.multiselect(
            "Categories",
            options=list(CATEGORY_MAP.keys()),
            default=list(CATEGORY_MAP.keys()),
        )
        min_score = st.slider("Minimum Score", 0.0, 1.0, 0.0)
        sources = st.multiselect(
            "Sources",
            options=list(INTEREST_CONFIG["source_weights"].keys()),
            default=list(INTEREST_CONFIG["source_weights"].keys()),
        )
        show_favorites = st.checkbox("Show Favorites Only", False)

    # Convert selected display names to internal topics
    selected_topics = [CATEGORY_MAP[name] for name in selected_categories]

    # Build query
    query = "SELECT id, title, url, summary, score, source, topic, is_favorite FROM posts WHERE score >= ?"
    params = [min_score]

    if sources:
        query += " AND source IN (" + ",".join(["?"] * len(sources)) + ")"
        params.extend(sources)

    if selected_topics:
        query += " AND topic IN (" + ",".join(["?"] * len(selected_topics)) + ")"
        params.extend(selected_topics)

    if show_favorites:
        query += " AND is_favorite = 1"

    query += " ORDER BY score DESC LIMIT 50"

    cursor = conn.cursor()
    cursor.execute(query, params)
    posts = cursor.fetchall()

    # Display posts
    if not posts:
        st.warning("No posts match your filters")
    else:
        for post in posts:
            post_id, title, url, summary, score, source, topic, is_favorite = post
            # Convert internal topic to display name
            display_topic = next(
                (name for name, cat in CATEGORY_MAP.items() if cat == topic), topic
            )

            with st.expander(f"{'⭐ ' if is_favorite else ''}{title} ({score:.2f})"):
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(f"**Source:** {source} | **Topic:** {display_topic}")
                    st.markdown(f"**Summary:** {summary}")
                    st.markdown(f"[Read more]({url})")
                with col2:
                    if st.button("⭐" if is_favorite else "☆", key=f"fav_{post_id}"):
                        cursor.execute(
                            "UPDATE posts SET is_favorite = ? WHERE id = ?",
                            (1 if not is_favorite else 0, post_id),
                        )
                        conn.commit()
                        st.rerun()

                # Feedback form
                with st.form(key=f"feedback_{post_id}"):
                    st.write("How was this recommendation?")
                    relevance = st.radio(
                        "Relevance", FEEDBACK_OPTIONS["relevance"], key=f"rel_{post_id}"
                    )
                    quality = st.radio(
                        "Quality", FEEDBACK_OPTIONS["quality"], key=f"qual_{post_id}"
                    )
                    novelty = st.radio(
                        "Novelty", FEEDBACK_OPTIONS["novelty"], key=f"nov_{post_id}"
                    )
                    notes = st.text_area("Additional notes", key=f"notes_{post_id}")

                    if st.form_submit_button("Submit Feedback"):
                        rel_score = FEEDBACK_OPTIONS["relevance"].index(relevance)
                        qual_score = FEEDBACK_OPTIONS["quality"].index(quality)
                        nov_score = FEEDBACK_OPTIONS["novelty"].index(novelty)
                        cursor.execute(
                            """
                            INSERT INTO feedback 
                            (post_id, relevance, quality, novelty, notes)
                            VALUES (?, ?, ?, ?, ?)
                        """,
                            (post_id, rel_score, qual_score, nov_score, notes),
                        )
                        conn.commit()
                        st.success("Thanks for your feedback!")

    conn.close()


if __name__ == "__main__":
    main()
