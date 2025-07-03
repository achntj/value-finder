# app.py
import streamlit as st
import sqlite3
from datetime import datetime
import subprocess
import time
from config import INTEREST_CONFIG

# Category mapping
CATEGORY_MAP = {
    config["name"]: category
    for category, config in INTEREST_CONFIG["categories"].items()
}

def get_db_connection():
    conn = sqlite3.connect("database.db")
    return conn

def debug_database(conn):
    """Debug database state and return status"""
    cursor = conn.cursor()
    debug_info = {"status": True, "messages": [], "stats": {}}

    try:
        # Check required tables exist
        required_tables = ['posts', 'discovered_sources', 'learning_feedback', 'source_penalties']
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

        cursor.execute("SELECT COUNT(*) FROM posts WHERE is_high_value = 1")
        debug_info["stats"]["high_value_posts"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM posts WHERE user_feedback IS NOT NULL")
        debug_info["stats"]["feedback_posts"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM posts WHERE value_score IS NOT NULL")
        debug_info["stats"]["scored_posts"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM discovered_sources WHERE is_active = 1")
        debug_info["stats"]["active_sources"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT source) FROM posts")
        debug_info["stats"]["unique_sources"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT topic) FROM posts")
        debug_info["stats"]["unique_topics"] = cursor.fetchone()[0]

        # Learning stats
        cursor.execute("SELECT COUNT(*) FROM learning_feedback WHERE feedback_type = 'false_positive'")
        debug_info["stats"]["false_positives"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM learning_feedback WHERE feedback_type = 'false_negative'")
        debug_info["stats"]["false_negatives"] = cursor.fetchone()[0]

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
    # Clean up low-value posts without feedback
    deleted = cursor.execute("""
        DELETE FROM posts 
        WHERE is_high_value = 0 
        AND user_feedback IS NULL 
        AND value_score < 0.3
    """).rowcount
    conn.commit()
    conn.close()
    st.success(f"Cleaned up {deleted} low-value posts")
    time.sleep(1)
    st.rerun()

def record_feedback(post_id, feedback_type, original_score, conn):
    """Record user feedback for learning"""
    cursor = conn.cursor()
    
    # Update post with feedback
    cursor.execute(
        "UPDATE posts SET user_feedback = ? WHERE id = ?",
        (feedback_type, post_id)
    )
    
    # Extract features for learning
    cursor.execute("""
        SELECT content, source, topic, value_score, novelty_score, interest_score
        FROM posts WHERE id = ?
    """, (post_id,))
    
    post_data = cursor.fetchone()
    if post_data:
        content, source, topic, value_score, novelty_score, interest_score = post_data
        
        # Simple feature extraction
        content_features = {
            "word_count": len(content.split()) if content else 0,
            "title_length": len(post_data[0].split()) if post_data[0] else 0,
            "has_technical_terms": any(term in content.lower() for term in 
                ["algorithm", "api", "framework", "system", "analysis", "research"]) if content else False,
            "source": source,
            "topic": topic
        }
        
        source_features = {
            "source_name": source,
            "topic": topic
        }
        
        # Record learning feedback
        cursor.execute("""
            INSERT INTO learning_feedback 
            (post_id, feedback_type, original_score, content_features, source_features)
            VALUES (?, ?, ?, ?, ?)
        """, (post_id, feedback_type, original_score, str(content_features), str(source_features)))
    
    conn.commit()

def main():
    st.set_page_config(page_title="Value Crawler", layout="wide", page_icon="💎")
    st.title("💎 Value Crawler - Goldmines from the Web")

    conn = get_db_connection()
    debug_info = debug_database(conn)

    with st.sidebar:
        st.header("🔧 Controls")
        if st.button("⏱️ Reset Scheduler"):
            reset_scheduler()
        if st.button("🧹 Cleanup Database"):
            cleanup_database()

        # Debug Info Section
        st.header("📊 System Status")
        if not debug_info["status"]:
            st.error("Database issues detected!")
            for msg in debug_info["messages"]:
                st.error(msg)
        else:
            st.success("System healthy")
            col1, col2 = st.columns(2)
            col1.metric("Total Posts", debug_info["stats"]["total_posts"])
            col2.metric("High Value", debug_info["stats"]["high_value_posts"])
            col1.metric("With Feedback", debug_info["stats"]["feedback_posts"])
            col2.metric("Active Sources", debug_info["stats"]["active_sources"])
            
            # Learning metrics
            st.subheader("🧠 Learning Stats")
            col1, col2 = st.columns(2)
            col1.metric("False Positives", debug_info["stats"]["false_positives"])
            col2.metric("False Negatives", debug_info["stats"]["false_negatives"])

        # Filters Section
        st.header("🔍 Filters")
        selected_categories = st.multiselect(
            "Categories",
            options=list(CATEGORY_MAP.keys()),
            default=list(CATEGORY_MAP.keys()),
        )
        sources = st.multiselect(
            "Sources",
            options=list(INTEREST_CONFIG["source_weights"].keys()),
            default=list(INTEREST_CONFIG["source_weights"].keys()),
        )

    # Main content area with two tabs
    tab1, tab2 = st.tabs(["💎 High Value Content", "🔍 Low Ranked Content (Learning)"])

    # Convert selected display names to internal topics
    selected_topics = [CATEGORY_MAP[name] for name in selected_categories]

    with tab1:
        st.header("💎 High Value Content")
        st.caption("Content the AI thinks is valuable - mark as 👎 if wrong to improve learning")
        
        # Build query for high-value content
        query = """
            SELECT p.id, p.title, p.url, p.summary, p.value_score, p.novelty_score, p.interest_score,
                   p.source, p.topic, p.user_feedback 
            FROM posts p
            WHERE p.is_high_value = 1
        """
        params = []

        if sources:
            query += " AND p.source IN (" + ",".join(["?"] * len(sources)) + ")"
            params.extend(sources)

        if selected_topics:
            query += " AND p.topic IN (" + ",".join(["?"] * len(selected_topics)) + ")"
            params.extend(selected_topics)

        query += " ORDER BY p.value_score DESC LIMIT 50"

        cursor = conn.cursor()
        cursor.execute(query, params)
        high_value_posts = cursor.fetchall()

        if not high_value_posts:
            st.warning("No high-value posts match your filters")
        else:
            for post in high_value_posts:
                (post_id, title, url, summary, value_score, novelty_score, 
                 interest_score, source, topic, user_feedback) = post
                
                # Convert internal topic to display name
                display_topic = next(
                    (name for name, cat in CATEGORY_MAP.items() if cat == topic), topic
                )

                # Color coding based on feedback
                if user_feedback == 'negative' or user_feedback == 'false_positive':
                    header_icon = "❌"
                    header_color = "red"
                elif user_feedback == 'positive':
                    header_icon = "✅"
                    header_color = "green"
                else:
                    header_icon = "💎"
                    header_color = "blue"
                    
                with st.expander(
                    f"{header_icon} {title} (Value: {value_score:.3f}, Novel: {novelty_score:.3f}, Interest: {interest_score:.3f})",
                    expanded=False
                ):                
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        st.markdown(f"**Source:** {source} | **Topic:** {display_topic}")
                        if summary:
                            st.markdown(f"**Summary:** {summary}")
                        st.markdown(f"[Read more]({url})")
                    with col2:
                        if not user_feedback:
                            if st.button("👍", key=f"pos_{post_id}", help="This is valuable"):
                                record_feedback(post_id, 'positive', value_score, conn)
                                st.success("✅ Marked as valuable!")
                                time.sleep(0.5)
                                st.rerun()
                            if st.button("👎", key=f"neg_{post_id}", help="This is not valuable"):
                                record_feedback(post_id, 'false_positive', value_score, conn)
                                st.error("❌ Marked as false positive - will learn!")
                                time.sleep(0.5)
                                st.rerun()
                        else:
                            st.markdown(f"<span style='color:{header_color}'>Feedback recorded!</span>", 
                                unsafe_allow_html=True)


    with tab2:
        st.header("🔍 Low Ranked Content (Learning View)")
        st.caption("Content the AI ranked low - mark as 👍 if valuable to improve discovery")
        
        # Build query for low-value content
        query = """
            SELECT p.id, p.title, p.url, p.summary, p.value_score, p.novelty_score, p.interest_score,
                   p.source, p.topic, p.user_feedback, p.is_high_value
            FROM posts p
            WHERE p.is_high_value = 0
        """
        params = []

        if sources:
            query += " AND p.source IN (" + ",".join(["?"] * len(sources)) + ")"
            params.extend(sources)

        if selected_topics:
            query += " AND p.topic IN (" + ",".join(["?"] * len(selected_topics)) + ")"
            params.extend(selected_topics)

        query += " ORDER BY p.value_score DESC LIMIT 100"

        cursor.execute(query, params)
        all_posts = cursor.fetchall()

        if not all_posts:
            st.warning("No posts match your filters")
        else:
            for post in all_posts:
                (post_id, title, url, summary, value_score, novelty_score, 
                 interest_score, source, topic, user_feedback, is_high_value) = post
                
                # Convert internal topic to display name
                display_topic = next(
                    (name for name, cat in CATEGORY_MAP.items() if cat == topic), topic
                )

                # Different styling based on value and feedback
                if user_feedback == 'negative' or user_feedback == 'false_positive':
                    header_icon = "❌"
                    header_color = "red"
                elif user_feedback == 'positive':
                    header_icon = "✅"
                    header_color = "green"
                else:
                    header_icon = "🔍"
                    header_color = "blue"
                with st.expander(
                    f"{header_icon} {title} (Value: {value_score:.3f}, Novel: {novelty_score:.3f}, Interest: {interest_score:.3f})",
                    expanded=False
                ):                
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        st.markdown(f"**Source:** {source} | **Topic:** {display_topic}")
                        if summary:
                            st.markdown(f"**Summary:** {summary}")
                        st.markdown(f"[Read more]({url})")
                    with col2:
                        if not user_feedback:
                            if st.button("👍", key=f"pos_all_{post_id}", help="This is valuable"):
                                feedback_type = 'false_negative'
                                record_feedback(post_id, feedback_type, value_score, conn)
                                st.success("✅ Marked as valuable!")
                                time.sleep(0.5)
                                st.rerun()
                            if st.button("👎", key=f"neg_all_{post_id}", help="This is not valuable"):
                                feedback_type = 'negative'
                                record_feedback(post_id, feedback_type, value_score, conn)
                                st.error("❌ Marked as not valuable!")
                                time.sleep(0.5)
                                st.rerun()
                        else:
                            st.markdown(f"<span style='color:{header_color}'>Feedback recorded!</span>", 
                                unsafe_allow_html=True)

    conn.close()

if __name__ == "__main__":
    main()
