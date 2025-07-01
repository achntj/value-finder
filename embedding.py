# embedding.py
import sqlite3
import numpy as np
import faiss
import json
from sentence_transformers import SentenceTransformer

DATABASE = "database.db"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
INDEX_FILE = "faiss.index"
ID_MAP_FILE = "id_map.json"

def build_index():
    model = SentenceTransformer(EMBEDDING_MODEL)
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute("SELECT id, summary FROM posts WHERE summary IS NOT NULL")
    rows = cursor.fetchall()

    embeddings = []
    ids = []
    id_map = {}

    for i, (post_id, summary) in enumerate(rows):
        vec = model.encode(summary)
        embeddings.append(vec)
        ids.append(i)
        id_map[i] = post_id

    if not embeddings:
        print("No embeddings to index.")
        return

    dim = len(embeddings[0])
    index = faiss.IndexIDMap(faiss.IndexFlatL2(dim))
    index.add_with_ids(np.array(embeddings).astype("float32"), np.array(ids))

    faiss.write_index(index, INDEX_FILE)
    with open(ID_MAP_FILE, "w") as f:
        json.dump(id_map, f)

    print("Embedding index built.")

if __name__ == "__main__":
    build_index()

