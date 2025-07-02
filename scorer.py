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


class ContentScorer:
    def __init__(self):
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self.conn = sqlite3.connect(DATABASE)
        self.categories = INTEREST_CONFIG["categories"]
        self.source_weights = INTEREST_CONFIG["source_weights"]
        self.category_keys = list(self.categories.keys())

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
            best_score *= source_weight

            scores.append(float(best_score))
            topics.append(int(best_topic_idx))  # Ensure topic is integer

        return scores, topics

    def apply_feedback_adjustments(self):
        cursor = self.conn.cursor()

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

        adjustments = {cat: [] for cat in self.categories}

        for topic, relevance, quality in feedback:
            try:
                # Handle both string topics (from DB) and integer indices
                if isinstance(topic, str):
                    topic_idx = self.category_keys.index(topic)
                else:
                    topic_idx = int(topic)

                cat = self.category_keys[topic_idx]
                score = (float(relevance) + float(quality)) / 6.0
                adjustments[cat].append(score)
            except (ValueError, IndexError) as e:
                print(f"Warning: Invalid topic '{topic}': {e}")
                continue

        for cat, scores in adjustments.items():
            if not scores:
                continue

            avg_score = np.mean(scores)
            current_weight = float(self.categories[cat]["weight"])
            new_weight = current_weight * (1 + LEARNING_RATE * (avg_score - 0.5))

            cursor.execute(
                """
                INSERT OR REPLACE INTO interest_profile 
                (category, current_weight, last_updated)
                VALUES (?, ?, ?)
            """,
                (cat, new_weight, datetime.now().isoformat()),
            )

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
                continue

        self.conn.commit()

    def run(self):
        print("Starting scoring process...")

        try:
            self.apply_feedback_adjustments()

            interest_embeddings = self.load_interest_embeddings()
            ids, _, post_embeddings, sources = self.get_post_embeddings()

            if not ids:
                print("No new posts to score.")
                return

            scores, topics = self.compute_scores(
                post_embeddings, interest_embeddings, sources
            )
            self.update_scores_in_db(ids, scores, topics)

            print(f"✅ Scored {len(ids)} posts.")
        except Exception as e:
            print(f"❌ Error in scoring process: {e}")
            raise

    def __del__(self):
        self.conn.close()


if __name__ == "__main__":
    scorer = ContentScorer()
    scorer.run()
