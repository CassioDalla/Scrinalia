from collections.abc import Collection
from typing import TYPE_CHECKING, Any, Literal, cast

import spacy

from scrinalia.core.language import get_language
from scrinalia.core.logger import logger
from scrinalia.domains.archive.schemas import ArchiveEntityDTO

if TYPE_CHECKING:
    from spacy.language import Language
    from spacy.pipeline import EntityRuler


class SpacyEngine:
    """
    Named Entity Recognition (NER) extraction engine using spaCy.

    ``spacy`` is imported at module level because it is relatively cheap; the trained
    pipeline is loaded on instantiation, which is where the real cost lives. The
    ``EntityRuler`` and ``Language`` imports are type-only so that merely importing
    the engine does not build the spacy pipeline modules.
    """

    def __init__(
        self,
        model: str | None = None,
        custom_rules: list[dict[str, Any]] | None = None,
        device: str = "gpu",
        **kwargs: Any,
    ) -> None:

        # The model is a property of the language, not of the engine: the default comes from the
        # active profile so a new language does not have to edit this engine or its presets.
        self.model_name = model or get_language().ner_model
        self.device = device
        self.disable = kwargs.get("disable", [])
        if "cpu" in self.device:
            spacy.require_cpu()  # type: ignore

        else:
            spacy.prefer_gpu()  # type: ignore

        try:
            self.nlp: Language = spacy.load(self.model_name, disable=self.disable)
        except OSError:
            logger.error(f"❌ Model {self.model_name} not found. Run: python -m spacy download {self.model_name}")
            raise

        # Injection of institutional rules (dynamic dictionaries from the Database)
        if custom_rules:
            ruler = cast("EntityRuler", self.nlp.add_pipe("entity_ruler", before="ner"))
            ruler.add_patterns(custom_rules)
            logger.info(f"⚙️ {len(custom_rules)} institutional rules loaded into the NER engine.")

    def extract(self, texts: list[str]) -> list[list[ArchiveEntityDTO]]:
        """
        Runs batch inference using nlp.pipe for maximum performance
        to extract Named Entities (PER, ORG, LOC).

        Applies Data Quality filters (string length) and removes
        exact duplicates within the same text context.

        Args:
            text (list[str]): List of concatenated texts from the document.

        Returns:
            list[ArchiveEntityDTO]: List of validated entity contracts.
        """
        if not texts:
            return []

        results: list[list[ArchiveEntityDTO]] = []
        allowed_labels = {"PER", "ORG", "LOC"}

        # nlp.pipe processes the texts in batches and optimizes memory/CPU usage
        for doc in self.nlp.pipe(texts):
            entities_found: list[ArchiveEntityDTO] = []
            seen_keys: set[tuple[str, str]] = set()

            for ent in doc.ents:
                if ent.label_ in allowed_labels:
                    # If the database rule found a canonical ID, use it
                    # Otherwise, use the normalized raw text.
                    clean_name = ent.ent_id_ if ent.ent_id_ else ent.text.strip().title()

                    # Data Quality barrier: avoids noise from stray characters or huge anomalies
                    if 2 < len(clean_name) < 150:
                        entity_type = cast(Literal["PER", "ORG", "LOC"], ent.label_)
                        key = (clean_name, entity_type)

                        if key not in seen_keys:
                            seen_keys.add(key)
                            entities_found.append(ArchiveEntityDTO(name=clean_name, entity_type=entity_type))
            # Adds the list of validated entities from this document to the final result
            results.append(entities_found)

        return results

    def lemmatize(self, text: str, stopwords: Collection[str]) -> list[str]:
        doc = self.nlp(text.lower())
        lemmas = []

        for token in doc:
            # Only accepts words that: are not punctuation, are not spaces, and are not stopwords

            if token.is_punct or token.is_space or token.like_num:
                continue

            lemma = token.lemma_
            # Ignores stopwords, tokens classified as stop by spaCy and 1-letter words (like 'º' or 'a')
            if lemma not in stopwords and not token.is_stop and len(lemma) > 2:
                lemmas.append(lemma)

        return lemmas
