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
    "Serendipitous insights"
]

DIVERSITY_PENALTY = 0.15  # Tune this!

def get_interest_embeddings(model):
    return model.encode(INTERESTS)

def get_post_embeddings(model, conn):
    cursor = conn.cursor()
    cursor.execute("SELECT id, content FROM posts WHERE content IS NOT NULL")
    rows = cursor.fetchall()
    ids = [r[0] for r in rows]
    texts = [r[1] for r in rows]
    embeddings = model.encode(texts)
    return ids, texts, embeddings

def compute_scores_and_topics(post_embeddings, interest_embeddings):
    scores = []
    topics = []
    for post_vec in post_embeddings:
        sims = util.cos_sim(post_vec, interest_embeddings).numpy().flatten()
        max_idx = np.argmax(sims)
        max_score = sims[max_idx]
        scores.append(float(max_score))
        topics.append(max_idx)  # index of topic with max similarity
    return scores, topics

def apply_diversity_penalty(scores, topics):
    adjusted_scores = []
    recent_topics = []

    for score, topic in zip(scores, topics):
        penalty = 0
        if topic in recent_topics:
            penalty = DIVERSITY_PENALTY
        adjusted_score = score - penalty
        adjusted_scores.append(adjusted_score)

        # Update recent topics window (size 3 for example)
        recent_topics.append(topic)
        if len(recent_topics) > 3:
            recent_topics.pop(0)

    return adjusted_scores

def update_scores_in_db(ids, scores, conn):
    cursor = conn.cursor()
    # cursor.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS score REAL")
    for post_id, score in zip(ids, scores):
        cursor.execute("UPDATE posts SET score = ? WHERE id = ?", (score, post_id))
    conn.commit()

def main():
    conn = sqlite3.connect(DATABASE)
    model = SentenceTransformer("all-MiniLM-L6-v2")

    interest_vecs = get_interest_embeddings(model)
    ids, texts, post_vecs = get_post_embeddings(model, conn)
    scores, topics = compute_scores_and_topics(post_vecs, interest_vecs)
    adjusted_scores = apply_diversity_penalty(scores, topics)
    update_scores_in_db(ids, adjusted_scores, conn)
    conn.close()

if __name__ == "__main__":
    main()

