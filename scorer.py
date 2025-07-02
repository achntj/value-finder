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
LEARNING_RATE = 0.1  # How quickly we adapt to feedback


class ContentScorer:
    def __init__(self):
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self.conn = sqlite3.connect(DATABASE)
        self.categories = INTEREST_CONFIG["categories"]
        self.source_weights = INTEREST_CONFIG["source_weights"]

    def load_interest_embeddings(self):
        """Load or create interest embeddings with current weights"""
        interest_texts = []
        self.weights = []

        for cat, config in self.categories.items():
            # Get current weight from profile if available
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT current_weight FROM interest_profile WHERE category = ?", (cat,)
            )
            row = cursor.fetchone()
            weight = row[0] if row else config["weight"]

            interest_texts.append(config["name"] + ": " + ", ".join(config["keywords"]))
            self.weights.append(weight)

        embeddings = self.model.encode(interest_texts, normalize_embeddings=True)
        return embeddings

    def get_post_embeddings(self):
        """Get embeddings for unscored posts"""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT id, content, source FROM posts 
            WHERE embedding IS NULL AND content IS NOT NULL
        """
        )
        rows = cursor.fetchall()

        ids = [r[0] for r in rows]
        texts = [r[1] for r in rows]
        sources = [r[2] for r in rows]

        if not texts:
            return [], [], [], []

        embeddings = self.model.encode(texts, normalize_embeddings=True)

        # Store embeddings for later use
        for post_id, embedding in zip(ids, embeddings):
            cursor.execute(
                "UPDATE posts SET embedding = ? WHERE id = ?",
                (embedding.tobytes(), post_id),
            )
        self.conn.commit()

        return ids, texts, embeddings, sources

    def compute_scores(self, post_embeddings, interest_embeddings, sources):
        """Compute scores with source weighting and diversity"""
        scores = []
        topics = []

        for i, post_vec in enumerate(post_embeddings):
            # Get similarity to each interest
            sims = util.cos_sim(post_vec, interest_embeddings).numpy().flatten()

            # Apply interest weights
            weighted_sims = sims * self.weights

            # Get best matching topic
            best_topic_idx = np.argmax(weighted_sims)
            best_score = weighted_sims[best_topic_idx]

            # Apply source weight
            source = sources[i]
            source_weight = self.source_weights.get(source, 1.0)
            best_score *= source_weight

            scores.append(float(best_score))
            topics.append(best_topic_idx)

        return scores, topics

    def apply_feedback_adjustments(self):
        """Update weights based on user feedback"""
        cursor = self.conn.cursor()

        # Get recent feedback
        cursor.execute(
            """
            SELECT p.topic, f.relevance, f.quality 
            FROM feedback f
            JOIN posts p ON f.post_id = p.id
            WHERE f.timestamp > datetime('now', '-7 days')
        """
        )
        feedback = cursor.fetchall()

        if not feedback:
            return

        # Calculate adjustments
        adjustments = {cat: [] for cat in self.categories}
        for topic, relevance, quality in feedback:
            cat = list(self.categories.keys())[topic]
            score = (relevance + quality) / 6  # Normalize to 0-1
            adjustments[cat].append(score)

        # Apply adjustments with learning rate
        for cat, scores in adjustments.items():
            avg_score = np.mean(scores)
            current_weight = self.categories[cat]["weight"]

            # Update weight - increase for positive feedback, decrease for negative
            new_weight = current_weight * (1 + LEARNING_RATE * (avg_score - 0.5))

            # Store updated weight
            cursor.execute(
                """
                INSERT OR REPLACE INTO interest_profile 
                (category, current_weight, last_updated)
                VALUES (?, ?, ?)
            """,
                (cat, new_weight, datetime.now()),
            )

        self.conn.commit()

    def update_scores_in_db(self, ids, scores, topics):
        """Store computed scores in database"""
        cursor = self.conn.cursor()

        for post_id, score, topic_idx in zip(ids, scores, topics):
            topic_name = list(self.categories.keys())[topic_idx]
            cursor.execute(
                """
                UPDATE posts 
                SET score = ?, topic = ?, last_updated = ?
                WHERE id = ?
            """,
                (score, topic_name, datetime.now(), post_id),
            )

        self.conn.commit()

    def run(self):
        """Main scoring pipeline"""
        print("Starting scoring process...")

        # Apply feedback adjustments first
        self.apply_feedback_adjustments()

        # Load embeddings
        interest_embeddings = self.load_interest_embeddings()
        ids, _, post_embeddings, sources = self.get_post_embeddings()

        if not ids:
            print("No new posts to score.")
            return

        # Compute scores
        scores, topics = self.compute_scores(
            post_embeddings, interest_embeddings, sources
        )

        # Update database
        self.update_scores_in_db(ids, scores, topics)

        print(f"✅ Scored {len(ids)} posts.")

    def __del__(self):
        self.conn.close()


if __name__ == "__main__":
    scorer = ContentScorer()
    scorer.run()
