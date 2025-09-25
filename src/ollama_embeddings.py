import sys
from typing import List

import requests


class OllamaEmbeddings:
    """Client for getting embeddings from Ollama API."""

    def __init__(
        self,
        model_name: str = "nomic-embed-text:v1.5",
        base_url: str = "http://localhost:11434",
        keep_alive: str = "10m",
    ):
        self.model_name = model_name
        self.base_url = base_url
        self.api_url = f"{base_url}/api/embeddings"
        self.keep_alive = keep_alive

        # Create a session for connection pooling
        self.session = requests.Session()

        # Simple LRU cache for embeddings (to avoid re-computing same text)
        self._embedding_cache = {}
        self._cache_max_size = 100  # Keep last 100 embeddings

    def get_embedding(self, text: str) -> List[float]:
        """Get embedding for a single text."""
        # Check cache first
        cache_key = hash(text)
        if cache_key in self._embedding_cache:
            return self._embedding_cache[cache_key]

        try:
            response = self.session.post(
                self.api_url,
                json={
                    "model": self.model_name,
                    "prompt": text,
                    "keep_alive": self.keep_alive,
                },
                timeout=30,
            )
            response.raise_for_status()
            embedding = response.json()["embedding"]

            # Cache the result
            self._cache_embedding(cache_key, embedding)

            return embedding
        except Exception as e:
            print(f"Error getting embedding: {e}", file=sys.stderr)
            # Return a zero vector as fallback
            return [0.0] * 768  # Assuming 768-dim embeddings, adjust if different

    def _cache_embedding(self, key: int, embedding: List[float]):
        """Cache an embedding with simple LRU eviction."""
        if len(self._embedding_cache) >= self._cache_max_size:
            # Remove oldest entry (simple FIFO, not true LRU for simplicity)
            oldest_key = next(iter(self._embedding_cache))
            del self._embedding_cache[oldest_key]

        self._embedding_cache[key] = embedding

    def __del__(self):
        """Clean up the session when the object is destroyed."""
        if hasattr(self, "session"):
            self.session.close()

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings for multiple texts."""
        return [self.get_embedding(text) for text in texts]

    def check_health(self) -> bool:
        """Check if the Ollama service is healthy and responsive.

        Returns:
            True if service is healthy, False otherwise
        """
        try:
            # First check if the API is reachable
            test_response = self.session.get(f"{self.base_url}/api/tags", timeout=5)
            test_response.raise_for_status()

            # Check if our model is available
            response_data = test_response.json()
            models = [
                model.get("name", "") for model in response_data.get("models", [])
            ]

            # If our model is not available, still consider it healthy if API works
            if self.model_name not in models:
                return True  # API is working, model might need to be pulled

            # Try a simple embedding with direct API call (avoid fallback logic)
            embedding_response = self.session.post(
                self.api_url,
                json={
                    "model": self.model_name,
                    "prompt": "test",
                    "keep_alive": self.keep_alive,
                },
                timeout=10,
            )
            embedding_response.raise_for_status()
            embedding_data = embedding_response.json()

            # Check if we got a real embedding (not empty or all zeros)
            embedding = embedding_data.get("embedding", [])
            if not embedding or len(embedding) == 0:
                return False

            # Check if it's not all zeros (which would indicate a fallback)
            return any(val != 0.0 for val in embedding[:10])  # Check first 10 values

        except Exception:
            return False

    def embed_text(self, text: str) -> List[float]:
        """Alias for get_embedding for compatibility."""
        return self.get_embedding(text)
