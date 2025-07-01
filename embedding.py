import sqlite3
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import json

DATABASE = "database.db"
INDEX_FILE = "faiss.index"

def build_index():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, content FROM posts WHERE content IS NOT NULL")
    rows = cursor.fetchall()

    model = SentenceTransformer("all-MiniLM-L6-v2")
    embeddings = [model.encode(content) for _, content in rows]
    ids = [post_id for post_id, _ in rows]

    embedding_dim = embeddings[0].shape[0]  # <-- Define embedding_dim here

    id_map = {i: post_id for i, post_id in enumerate(ids)}
    id_to_faiss = list(id_map.keys())

    index = faiss.IndexIDMap(faiss.IndexFlatL2(embedding_dim))
    index.add_with_ids(np.array(embeddings), np.array(id_to_faiss, dtype="int64"))
    
    with open("id_map.json", "w") as f:
        json.dump(id_map, f)

    conn.close()

if __name__ == "__main__":
    build_index()

