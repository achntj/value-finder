# app.py
import streamlit as st
import sqlite3
from datetime import datetime
import subprocess
import time
from config import INTEREST_CONFIG, FEEDBACK_OPTIONS

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
        # Check required tables exist
        required_tables = ['posts', 'flagged_content', 'source_penalties']
        for table in required_tables:
            cursor.execute(
                f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'"
            )
            if not cursor.fetchone():
                debug_info["status"] = False
                debug_info["messages"].append(f"Missing table: {table}")

        # Get database stats
        cursor.execute("SELECT COUNT(*) FROM posts")
        debug_info["stats"]["total_posts"] = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) FROM posts p
            JOIN flagged_content fc ON p.id = fc.post_id
        """)
        debug_info["stats"]["flagged_posts"] = cursor.fetchone()[0]

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
    deleted = cursor.execute("DELETE FROM posts WHERE is_favorite = 0").rowcount
    conn.commit()
    conn.close()
    st.success(f"Cleaned up {deleted} non-favorite posts")
    time.sleep(1)
    st.rerun()


def flag_content(post_id, source, reason, severity):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # First check if already flagged
        cursor.execute(
            "SELECT 1 FROM flagged_content WHERE post_id = ?", 
            (post_id,)
        )
        if cursor.fetchone():
            st.warning("This content was already flagged")
            conn.close()
            return False

        # Flag the content
        cursor.execute(
            """
            INSERT INTO flagged_content 
            (post_id, reason, severity, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            (post_id, reason, severity, datetime.now().isoformat()),
        )

        # Apply immediate score penalty
        penalty = 0.7 if severity >= 2 else 0.9
        cursor.execute(
            "UPDATE posts SET score = score * ? WHERE id = ?",
            (penalty, post_id),
        )

        # Penalize the source
        cursor.execute(
            """
            INSERT OR REPLACE INTO source_penalties 
            (source, penalty_score, last_flagged)
            VALUES (?, ?, ?)
            """,
            (source, 0.8, datetime.now().isoformat()),
        )

        conn.commit()
        st.success("Content flagged and source penalized!")
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Error flagging content: {e}")
        return False
    finally:
        conn.close()

def main():
    st.set_page_config(page_title="WebScout", layout="centered", page_icon="🔍")
    st.title("Your Smart Daily Digest")

    conn = get_db_connection()
    debug_info = debug_database(conn)

    with st.sidebar:
        st.header("Controls")
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
            cols[1].metric("Flagged", debug_info["stats"]["flagged_posts"])
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
        hide_flagged = st.checkbox("Hide Flagged Content", True)

    # Convert selected display names to internal topics
    selected_topics = [CATEGORY_MAP[name] for name in selected_categories]

    # Build query
    query = """
        SELECT p.id, p.title, p.url, p.summary, p.score, 
               p.source, p.topic, p.is_favorite 
        FROM posts p
        WHERE p.score >= ?
    """
    params = [min_score]

    # Add filters
    if sources:
        query += " AND p.source IN (" + ",".join(["?"] * len(sources)) + ")"
        params.extend(sources)

    if selected_topics:
        query += " AND p.topic IN (" + ",".join(["?"] * len(selected_topics)) + ")"
        params.extend(selected_topics)

    if show_favorites:
        query += " AND p.is_favorite = 1"

    if hide_flagged:
        query += """
            AND NOT EXISTS (
                SELECT 1 FROM flagged_content fc 
                WHERE fc.post_id = p.id
            )
        """

    query += " ORDER BY p.score DESC LIMIT 50"

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

                # Unified rating form
                # Store the rating choice in session state to maintain UI consistency
                if f"rating_{post_id}" not in st.session_state:
                    st.session_state[f"rating_{post_id}"] = None

                # Unified rating form
                with st.form(key=f"rating_form_{post_id}"):
                    # Get or update the rating choice
                    rating_choice = st.radio(
                        "Rate this content:",
                        options=["👍 Good", "👎 Bad"],
                        horizontal=True,
                        key=f"rating_input_{post_id}",
                        index=0 if st.session_state[f"rating_{post_id}"] != "👎 Bad" else 1
                    )
                    
                    # Update session state when rating changes
                    if rating_choice != st.session_state[f"rating_{post_id}"]:
                        st.session_state[f"rating_{post_id}"] = rating_choice
                        st.rerun()  # Needed to immediately update the form
                    
                    # Fields that always appear
                    notes = st.text_area("Additional comments (optional)", key=f"notes_{post_id}")
                    
                    # Conditional fields for negative feedback
                    if st.session_state[f"rating_{post_id}"] == "👎 Bad":
                        reason = st.selectbox(
                            "What was wrong?",
                            ["Ad/Sponsored", "Low Quality", "Off-Topic", "Misleading"],
                            key=f"reason_{post_id}",
                        )
                        severity = st.slider(
                            "How severe?", 1, 3, 1, 
                            help="1=Minor, 2=Moderate, 3=Major",
                            key=f"severity_{post_id}"
                        )
                    else:
                        # Fields for positive feedback
                        quality = st.radio(
                            "Quality rating",
                            FEEDBACK_OPTIONS["quality"],
                            key=f"qual_{post_id}",
                            horizontal=True
                        )
                    
                    if st.form_submit_button("Submit Rating"):
                        if st.session_state[f"rating_{post_id}"] == "👎 Bad":
                            # Handle negative rating (flag content)
                            flag_content(post_id, source, reason, severity)
                            
                            # Also record as negative feedback
                            cursor.execute(
                                """
                                INSERT INTO feedback 
                                (post_id, quality, notes, rating_type)
                                VALUES (?, ?, ?, ?)
                                """,
                                (post_id, 0, notes, "negative"),
                            )
                            conn.commit()
                            st.success("Thanks for your feedback - content has been flagged")
                        else:
                            # Handle positive rating (record feedback)
                            qual_score = FEEDBACK_OPTIONS["quality"].index(quality)
                            cursor.execute(
                                """
                                INSERT INTO feedback 
                                (post_id, quality, notes, rating_type)
                                VALUES (?, ?, ?, ?)
                                """,
                                (post_id, qual_score, notes, "positive"),
                            )
                            conn.commit()
                            st.success("Thanks for your feedback!")
                        
                        # Clear the rating state after successful submission
                        st.session_state[f"rating_{post_id}"] = None
                        time.sleep(1)
                        st.rerun()
    conn.close()


if __name__ == "__main__":
    main()
