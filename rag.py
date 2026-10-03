import os
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from redisvl.index import SearchIndex
from redisvl.query import AggregateHybridQuery

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

embeddings = OpenAIEmbeddings(
    model="text-embedding-3-small",
    api_key=os.getenv("AVALAI_API_KEY"),
    base_url="https://api.avalai.ir/v1",
    check_embedding_ctx_length=False,
)

schema = {
    "index": {"name": "docs", "prefix": "doc"},
    "fields": [
        {"name": "text", "type": "text"},
        {"name": "source", "type": "tag"},
        {
            "name": "embedding",
            "type": "vector",
            "attrs": {"dims": 1536, "distance_metric": "cosine", "algorithm": "flat", "datatype": "float32"},
        },
    ],
}
index = SearchIndex.from_dict(schema, redis_url=REDIS_URL)


def load_chunks():
    chunks = []
    for path in Path("docs").glob("*.md"):
        text = path.read_text(encoding="utf-8")
        title = text.splitlines()[0].lstrip("# ")
        for section in text.split("\n## ")[1:]:
            chunks.append({"text": f"{title} - {section.strip()}", "source": path.name})
    return chunks


def build_index():
    chunks = load_chunks()
    vectors = embeddings.embed_documents([c["text"] for c in chunks])
    for chunk, vector in zip(chunks, vectors):
        chunk["embedding"] = np.array(vector, dtype=np.float32).tobytes()
    index.create(overwrite=True, drop=True)
    index.load(chunks)
    print(f"indexed {len(chunks)} chunks")


def search(question, k=3):
    query = AggregateHybridQuery(
        text=question,
        text_field_name="text",
        vector=embeddings.embed_query(question),
        vector_field_name="embedding",
        alpha=0.7,
        num_results=k,
        return_fields=["text", "source"],
        stopwords=None,
    )
    return index.query(query)


if __name__ == "__main__":
    build_index()
