from typing import Any


class SentenceTransformerEngine:
    """
    Embedding engine backed by sentence-transformers.

    ``sentence_transformers`` is imported inside ``__init__`` on purpose: it drags in
    torch and transformers, and the API reaches this engine only on a semantic search,
    so a lexical request must not pay that import.

    Embeddings are normalized, which makes the cosine distance well behaved and keeps
    the similarity in a stable range regardless of the text length.
    """

    def __init__(
        self,
        model: str = "paraphrase-multilingual-MiniLM-L12-v2",
        device: str = "cpu",
        batch_size: int = 32,
        dimensions: int | None = None,
        **kwargs: Any,
    ) -> None:
        from sentence_transformers import SentenceTransformer

        self.batch_size = batch_size
        # The expected dimension of the model, so a model swap that changes it fails with
        # a clear message here instead of a cryptic dimension error from PostgreSQL.
        self.dimensions = dimensions
        self.model = SentenceTransformer(model, device=device)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embeds a batch of texts, returning one vector per text."""
        if not texts:
            return []

        vectors = self.model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        result = [vector.tolist() for vector in vectors]

        if self.dimensions is not None:
            for vector in result:
                if len(vector) != self.dimensions:
                    raise ValueError(
                        f"Embedding model produced {len(vector)} dimensions, but the schema expects "
                        f"{self.dimensions}. Update EMBEDDING_DIMENSIONS and the migration together."
                    )

        return result
