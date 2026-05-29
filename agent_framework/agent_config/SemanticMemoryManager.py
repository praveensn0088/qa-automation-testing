import chromadb

class SemanticMemoryManager:
    def __init__(self, persist_path: str, collection_name: str = "ltm"):
        # ✅ Use new ChromaDB PersistentClient API
        self.client = chromadb.PersistentClient(path=persist_path)

        # ✅ Create or get collection
        self.collection = self.client.get_or_create_collection(name=collection_name)

    def add(self, ids, documents=None, embeddings=None, metadatas=None):
        self.collection.add(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)

    def query(self, query_text, top_k=3):
        return self.collection.query(query_texts=[query_text], n_results=top_k)

    def delete(self, ids):
        self.collection.delete(ids=ids)

    def count(self):
        return self.collection.count()