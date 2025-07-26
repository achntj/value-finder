# embedding.py
import sqlite3
import numpy as np
import faiss
import json
from sentence_transformers import SentenceTransformer
from config import INTEREST_CONFIG

DATABASE = "database.db"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
INDEX_FILE = "faiss.index"
ID_MAP_FILE = "id_map.json"


class EmbeddingIndexer:
    def __init__(self):
        self.model = SentenceTransformer(EMBEDDING_MODEL)
        self.conn = sqlite3.connect(DATABASE)

    def build_index(self):
        """Build or update the FAISS index"""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT id, summary, value_score FROM posts 
            WHERE summary IS NOT NULL
            ORDER BY score DESC
            LIMIT 1000  # Only index top content
        """
        )
        rows = cursor.fetchall()

        if not rows:
            print("No posts to index.")
            return

        # Prepare embeddings
        embeddings = []
        ids = []
        id_map = {}

        for i, (post_id, summary, score) in enumerate(rows):
            vec = self.model.encode(summary)
            embeddings.append(vec)
            ids.append(i)
            id_map[i] = (post_id, score)  # Store both ID and score

        dim = len(embeddings[0])

        # Try to load existing index to update
        try:
            index = faiss.read_index(INDEX_FILE)
            print("Loaded existing index to update.")
        except:
            index = faiss.IndexIDMap(faiss.IndexFlatL2(dim))
            print("Created new index.")

        index.add_with_ids(np.array(embeddings).astype("float32"), np.array(ids))

        # Save index and mappings
        faiss.write_index(index, INDEX_FILE)
        with open(ID_MAP_FILE, "w") as f:
            json.dump(id_map, f)

        print(f"Embedding index built with {len(embeddings)} posts.")

    def __del__(self):
        self.conn.close()


if __name__ == "__main__":
    indexer = EmbeddingIndexer()
    indexer.build_index()
