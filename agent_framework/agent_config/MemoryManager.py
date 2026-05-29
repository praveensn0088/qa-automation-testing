import json
from pathlib import Path
from agent_framework.agent_config.SemanticMemoryManager import SemanticMemoryManager
from agent_framework.utils.utils import normalize_embeddings
from agent_framework.utils.logger import logger

class ShortTermMemory:
    def __init__(self):
        self.memory = {}

    def update(self, key, value):
        self.memory[key] = value

    def get(self, key):
        return self.memory.get(key)

    def clear(self):
        self.memory.clear()


class LongTermMemory:
    def __init__(self, storage_path: str, use_chroma: bool = False):
        self.use_chroma = use_chroma

        if use_chroma:
            self.chroma = SemanticMemoryManager(persist_path=str(Path(storage_path) / "chroma"))
        else:
            self.storage_path = Path(storage_path)
            self.storage_path.mkdir(parents=True, exist_ok=True)

            storage_dir = self.storage_path / "storage"
            storage_dir.mkdir(parents=True, exist_ok=True)

            self.memory_file = storage_dir / "ltm.json"
            if not self.memory_file.exists():
                self.memory_file.write_text(json.dumps({}))

    def save(self, key, value):
        if value is None or value == "":
            logger.warning(f"Skipping save for key '{key}' due to empty value.")
            return

        if isinstance(value, dict) and "embedding" in value:
            emb = value["embedding"]
            if isinstance(emb, (list, tuple)) and emb:
                try:
                    value["embedding"] = normalize_embeddings(emb)
                except Exception as e:
                    logger.warning(f"Failed to normalize embedding for key '{key}': {e}")
        elif isinstance(value, (list, tuple)) and value:
            first = value[0]
            if isinstance(first, (float, int, list, tuple)):
                try:
                    value = normalize_embeddings(value)
                except Exception as e:
                    logger.warning(f"Failed to normalize embeddings for key '{key}': {e}")

        if self.use_chroma:
            if isinstance(value, (dict, list)):
                value_to_store = json.dumps(value)
            else:
                value_to_store = str(value)

            self.chroma.add(ids=[key], documents=[value_to_store])
        elif hasattr(self, "memory_file"):
            data = self._load_memory()
            data[key] = value
            self._write_memory(data)
        else:
            raise AttributeError("No valid storage mechanism found for LongTermMemory.")

    def retrieve(self, key):
        if self.use_chroma:
            results = self.chroma.query(key, top_k=1)
            if results.get("documents") and results["documents"][0]:
                doc = results["documents"][0][0]
                try:
                    return json.loads(doc)
                except Exception:
                    return doc
            return None
        else:
            data = self._load_memory()
            return data.get(key)

    def all(self):
        if self.use_chroma:
            return "ChromaDB does not support full memory dump."
        else:
            return self._load_memory()

    def _load_memory(self):
        try:
            return json.loads(self.memory_file.read_text())
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def _write_memory(self, data):
        self.memory_file.write_text(json.dumps(data, indent=2))
