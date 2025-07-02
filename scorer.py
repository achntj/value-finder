# scorer.py
import sqlite3
import numpy as np
from sentence_transformers import SentenceTransformer, util
from datetime import datetime
import json
from config import INTEREST_CONFIG

DATABASE = "database.db"
DIVERSITY_WINDOW = 3
DIVERSITY_PENALTY = 0.15
LEARNING_RATE = 0.1
FLAGGED_PENALTY = 0.5  # Score multiplier for flagged content
SOURCE_PENALTY_THRESHOLD = 0.6  # Minimum source reliability score


class ContentScorer:
    def __init__(self):
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self.conn = sqlite3.connect(DATABASE)
        self.categories = INTEREST_CONFIG["categories"]
        self.source_weights = INTEREST_CONFIG["source_weights"]
        self.category_keys = list(self.categories.keys())

    def apply_source_penalties(self):
        """Apply source reliability penalties to posts"""
        cursor = self.conn.cursor()

        # Apply source penalties
        cursor.execute(
            """
            UPDATE posts
            SET score = score * (
                SELECT COALESCE(penalty_score, 1.0)
                FROM source_penalties
                WHERE source = posts.source
            )
            WHERE EXISTS (
                SELECT 1 FROM source_penalties
                WHERE source = posts.source
            )
        """
        )

        # Apply additional penalty for flagged content
        cursor.execute(
            """
            UPDATE posts
            SET score = score * ?
            WHERE id IN (
                SELECT post_id FROM flagged_content
                WHERE severity >= 2
            )
        """,
            (FLAGGED_PENALTY,),
        )

        # Completely hide content from banned sources
        cursor.execute(
            """
            DELETE FROM posts
            WHERE source IN (
                SELECT source FROM source_penalties
                WHERE penalty_score < ?
            )
        """,
            (SOURCE_PENALTY_THRESHOLD,),
        )

        self.conn.commit()

    def load_interest_embeddings(self):
        interest_texts = []
        self.weights = []

        for cat, config in self.categories.items():
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT current_weight FROM interest_profile 
                WHERE category = ?
            """,
                (cat,),
            )
            row = cursor.fetchone()
            weight = float(row[0]) if row else float(config["weight"])

            interest_texts.append(config["name"] + ": " + ", ".join(config["keywords"]))
            self.weights.append(weight)

        embeddings = self.model.encode(interest_texts, normalize_embeddings=True)
        return embeddings

    def get_post_embeddings(self):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT id, content, source FROM posts 
            WHERE embedding IS NULL AND content IS NOT NULL
            AND id NOT IN (
                SELECT post_id FROM flagged_content 
                WHERE severity >= 3
            )
        """
        )
        rows = cursor.fetchall()

        if not rows:
            return [], [], [], []

        ids = [r[0] for r in rows]
        texts = [r[1] for r in rows]
        sources = [r[2] for r in rows]
        embeddings = self.model.encode(texts, normalize_embeddings=True)

        for post_id, embedding in zip(ids, embeddings):
            cursor.execute(
                """
                UPDATE posts SET embedding = ? 
                WHERE id = ?
            """,
                (embedding.tobytes(), post_id),
            )
        self.conn.commit()

        return ids, texts, embeddings, sources

    def compute_scores(self, post_embeddings, interest_embeddings, sources):
        scores = []
        topics = []

        for i, post_vec in enumerate(post_embeddings):
            sims = util.cos_sim(post_vec, interest_embeddings).numpy().flatten()
            weighted_sims = sims * self.weights

            best_topic_idx = np.argmax(weighted_sims)
            best_score = weighted_sims[best_topic_idx]

            source = sources[i]
            source_weight = self.source_weights.get(source, 1.0)

            # Apply source penalties
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT penalty_score FROM source_penalties WHERE source = ?", (source,)
            )
            penalty_row = cursor.fetchone()
            if penalty_row:
                source_weight *= float(penalty_row[0])

            best_score *= source_weight

            scores.append(float(best_score))
            topics.append(int(best_topic_idx))

        return scores, topics

    def apply_feedback_adjustments(self):
        cursor = self.conn.cursor()

        # Process negative feedback (for penalties)
        cursor.execute(
            """
            SELECT p.topic, f.quality, f.notes
            FROM feedback f
            JOIN posts p ON f.post_id = p.id
            WHERE f.timestamp > datetime('now', '-7 days')
            AND f.rating_type = 'negative'
            AND f.quality IS NOT NULL
            """
        )
        negative_feedback = cursor.fetchall()

        if negative_feedback:
            adjustments = {cat: [] for cat in self.categories}

            for topic, quality, notes in negative_feedback:
                try:
                    if isinstance(topic, str):
                        topic_idx = self.category_keys.index(topic)
                    else:
                        topic_idx = int(topic)

                    cat = self.category_keys[topic_idx]
                    # Convert quality (0-2 scale) to 0-1 range
                    normalized_quality = float(quality) / 2.0
                    adjustments[cat].append(normalized_quality)
                except (ValueError, IndexError) as e:
                    logger.warning(f"Invalid topic '{topic}' in feedback: {e}")
                    continue

            for cat, qualities in adjustments.items():
                if qualities:
                    avg_quality = np.mean(qualities)
                    current_weight = float(self.categories[cat]["weight"])
                    # Decrease weight for negative feedback (0.8-1.0 factor)
                    new_weight = current_weight * (0.8 + (0.2 * (1 - avg_quality)))

                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO interest_profile 
                        (category, current_weight, last_updated)
                        VALUES (?, ?, ?)
                        """,
                        (cat, new_weight, datetime.now().isoformat()),
                    )

        # Process positive feedback (for rewards)
        cursor.execute(
            """
            SELECT p.topic, f.quality
            FROM feedback f
            JOIN posts p ON f.post_id = p.id
            WHERE f.timestamp > datetime('now', '-7 days')
            AND f.rating_type = 'positive'
            AND f.quality IS NOT NULL
            """
        )
        positive_feedback = cursor.fetchall()

        if positive_feedback:
            positive_adjustments = {cat: [] for cat in self.categories}

            for topic, quality in positive_feedback:
                try:
                    if isinstance(topic, str):
                        topic_idx = self.category_keys.index(topic)
                    else:
                        topic_idx = int(topic)

                    cat = self.category_keys[topic_idx]
                    # Convert quality (0-2 scale) to 0-1 range
                    normalized_quality = float(quality) / 2.0
                    positive_adjustments[cat].append(normalized_quality)
                except (ValueError, IndexError) as e:
                    logger.warning(f"Invalid topic '{topic}' in feedback: {e}")
                    continue

            for cat, qualities in positive_adjustments.items():
                if qualities:
                    avg_quality = np.mean(qualities)
                    current_weight = float(self.categories[cat]["weight"])
                    # Increase weight for positive feedback (1.0-1.2 factor)
                    new_weight = current_weight * (1.0 + (0.2 * avg_quality))

                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO interest_profile 
                        (category, current_weight, last_updated)
                        VALUES (?, ?, ?)
                        """,
                        (cat, new_weight, datetime.now().isoformat()),
                    )

        # Rest of the method (flagged content processing) remains the same...
        # Process flagged content patterns
        cursor.execute(
            """
            SELECT p.topic, fc.reason, COUNT(*) as flag_count
            FROM flagged_content fc
            JOIN posts p ON fc.post_id = p.id
            WHERE fc.timestamp > datetime('now', '-7 days')
            GROUP BY p.topic, fc.reason
            HAVING flag_count > 2
            """
        )
        flag_patterns = cursor.fetchall()

        for topic, reason, count in flag_patterns:
            try:
                if isinstance(topic, str):
                    topic_idx = self.category_keys.index(topic)
                else:
                    topic_idx = int(topic)

                cat = self.category_keys[topic_idx]
                # Significant weight reduction for problematic topics
                cursor.execute(
                    """
                    UPDATE interest_profile
                    SET current_weight = current_weight * 0.7
                    WHERE category = ?
                    """,
                    (cat,),
                )
            except (ValueError, IndexError) as e:
                logger.warning(f"Invalid topic '{topic}' in flag patterns: {e}")

        self.conn.commit()

    def update_scores_in_db(self, ids, scores, topics):
        cursor = self.conn.cursor()

        for post_id, score, topic_idx in zip(ids, scores, topics):
            try:
                topic_name = self.category_keys[int(topic_idx)]
                cursor.execute(
                    """
                    UPDATE posts 
                    SET score = ?, topic = ?, last_updated = ?
                    WHERE id = ?
                """,
                    (float(score), topic_name, datetime.now().isoformat(), post_id),
                )
            except (ValueError, IndexError) as e:
                print(
                    f"Warning: Invalid topic index {topic_idx} for post {post_id}: {e}"
                )

        self.conn.commit()

    def run(self):
        print("Starting scoring process...")

        try:
            # Apply penalties first
            self.apply_source_penalties()

            # Process feedback and flags
            self.apply_feedback_adjustments()

            # Score new content
            interest_embeddings = self.load_interest_embeddings()
            ids, _, post_embeddings, sources = self.get_post_embeddings()

            if ids:
                scores, topics = self.compute_scores(
                    post_embeddings, interest_embeddings, sources
                )
                self.update_scores_in_db(ids, scores, topics)
                print(f"✅ Scored {len(ids)} posts.")
            else:
                print("No new posts to score.")

        except Exception as e:
            print(f"❌ Error in scoring process: {e}")
            raise

    def __del__(self):
        self.conn.close()


if __name__ == "__main__":
    scorer = ContentScorer()
    scorer.run()
