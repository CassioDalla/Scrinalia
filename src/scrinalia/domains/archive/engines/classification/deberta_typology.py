from typing import Any, cast


class DebertaEngine:
    """
    Zero-shot classification engine backed by mDeBERTa.

    ``transformers`` is imported inside ``__init__``: it costs about a second on its
    own and is only needed once an engine is actually built, never just because a
    registry was consulted.
    """

    def __init__(
        self,
        model: str = "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli",
        device: str = "cpu",
        truncation: bool = True,
        max_length: int = 512,
        **kwargs: Any,
    ) -> None:
        from transformers import pipeline

        self.classifier = pipeline(
            "zero-shot-classification",
            model=model,
            device=device,
            truncation=truncation,
            max_length=max_length,
            **kwargs,
        )

    def classify(self, texts: list[str], candidate_labels: list[str], **kwargs: Any) -> list[dict]:
        results = self.classifier(texts, candidate_labels, **kwargs)
        # The pipeline's ``__call__`` is unannotated, so transformers infers a union that includes
        # the streaming iterator; this call never streams and answers one dict per text.
        return cast("list[dict]", results if isinstance(results, list) else [results])
