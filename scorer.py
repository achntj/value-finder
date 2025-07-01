import sqlite3
import numpy as np
from sentence_transformers import SentenceTransformer, util

DATABASE = "database.db"

INTERESTS = [
    "Latest AI models and research",
    "Philosophy and mental clarity",
    "Productivity systems and deep work",
    "Writing and creativity frameworks",
    "Startup advice and indie hacking",
    "Macro trends and investing",
    "Serendipitous insights",
]

DIVERSITY_WINDOW = 3
DIVERSITY_PENALTY = 0.15


def get_interest_embeddings(model):
    return model.encode(INTERESTS, normalize_embeddings=True)


def get_post_embeddings(model, conn):
    cursor = conn.cursor()
    cursor.execute("SELECT id, content FROM posts WHERE content IS NOT NULL")
    rows = cursor.fetchall()
    ids = [r[0] for r in rows]
    texts = [r[1] for r in rows]
    embeddings = model.encode(texts, normalize_embeddings=True)
    return ids, texts, embeddings


def compute_scores_and_topics(post_embeddings, interest_embeddings):
    scores = []
    topics = []
    for post_vec in post_embeddings:
        sims = util.cos_sim(post_vec, interest_embeddings).numpy().flatten()
        best_topic_idx = np.argmax(sims)
        best_score = sims[best_topic_idx]
        scores.append(float(best_score))
        topics.append(best_topic_idx)
    return scores, topics


def apply_diversity_penalty(scores, topics, window_size=DIVERSITY_WINDOW):
    adjusted_scores = []
    recent_topics = []

    for score, topic in zip(scores, topics):
        penalty = DIVERSITY_PENALTY if topic in recent_topics else 0
        adjusted_scores.append(score - penalty)

        recent_topics.append(topic)
        if len(recent_topics) > window_size:
            recent_topics.pop(0)

    return adjusted_scores


def update_scores_in_db(ids, scores, topics, conn):
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE posts ADD COLUMN topic TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists
    try:
        cursor.execute("ALTER TABLE posts ADD COLUMN score REAL")
    except sqlite3.OperationalError:
        pass  # column already exists

    for post_id, score, topic_idx in zip(ids, scores, topics):
        cursor.execute(
            "UPDATE posts SET score = ?, topic = ? WHERE id = ?",
            (score, INTERESTS[topic_idx], post_id),
        )

    conn.commit()


def main():
    print("Scoring posts by interest relevance + diversity...")
    conn = sqlite3.connect(DATABASE)
    model = SentenceTransformer("all-MiniLM-L6-v2")

    interest_vecs = get_interest_embeddings(model)
    ids, _, post_vecs = get_post_embeddings(model, conn)
    scores, topics = compute_scores_and_topics(post_vecs, interest_vecs)
    adjusted_scores = apply_diversity_penalty(scores, topics)
    update_scores_in_db(ids, adjusted_scores, topics, conn)
    conn.close()
    print("Scoring complete.")


if __name__ == "__main__":
    main()
