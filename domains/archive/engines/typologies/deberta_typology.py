from transformers import pipeline


class DebertaEngine:
    def __init__(
        self, model="MoritzLaurer/mDeBERTa-v3-base-mnli-xnli", device="cpu", truncation=True, max_length=512, **kwargs
    ):
        self.classifier = pipeline(
            "zero-shot-classification",
            model=model,
            device=device,
            truncation=truncation,
            max_length=max_length,
            **kwargs,
        )

    def classify(self, texts: list[str], candidate_labels: list[str], **kwargs) -> list[dict]:
        results = self.classifier(texts, candidate_labels, **kwargs)
        return results if isinstance(results, list) else [results]
