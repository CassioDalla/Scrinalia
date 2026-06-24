from typing import Any, Literal, cast

import spacy
from spacy.language import Language
from spacy.pipeline import EntityRuler

from core.logger import logger
from domains.archive.schemas import ArchiveEntityDTO


class SpacyEngine:
    """
    Motor de Extração de Entidades Nomeadas (NER) utilizando spaCy.
    """

    def __init__(
        self,
        model: str = "pt_core_news_lg",
        custom_rules: list[dict[str, Any]] | None = None,
        device: str = "gpu",
        **kwargs: Any,
    ) -> None:

        self.model_name = model
        self.device = device
        self.disable = kwargs.get("disable", [])
        if "cpu" in self.device:
            spacy.require_cpu()  # type: ignore

        else:
            spacy.prefer_gpu()  # type: ignore

        try:
            self.nlp: Language = spacy.load(self.model_name, disable=self.disable)
        except OSError:
            logger.error(
                f"❌ Modelo {self.model_name} não encontrado. Execute: python -m spacy download {self.model_name}"
            )
            raise

        # Injeção das regras institucionais (Dicionários dinâmicos do Banco de Dados)
        if custom_rules:
            ruler = cast(EntityRuler, self.nlp.add_pipe("entity_ruler", before="ner"))
            ruler.add_patterns(custom_rules)
            logger.info(f"⚙️ {len(custom_rules)} regras institucionais carregadas no motor NER.")

    def extract(self, texts: list[str]) -> list[list[ArchiveEntityDTO]]:
        """
        Executa a inferência em lote usando nlp.pipe para máxima performance
        para extrair Entidades Nomeadas (PER, ORG, LOC).

        Aplica filtros de Qualidade de Dados (tamanho de string) e remove
        duplicidades exatas dentro do mesmo contexto de texto.

        Args:
            text (list[str]): Lista de textos concatenado do documento.

        Returns:
            list[ArchiveEntityDTO]: Lista de contratos de entidades validados.
        """
        if not texts:
            return []

        results: list[list[ArchiveEntityDTO]] = []
        allowed_labels = {"PER", "ORG", "LOC"}

        # nlp.pipe processa os textos em lote e otimiza o uso da memória/CPU
        for doc in self.nlp.pipe(texts):
            entities_found: list[ArchiveEntityDTO] = []
            seen_keys: set[tuple[str, str]] = set()

            for ent in doc.ents:
                if ent.label_ in allowed_labels:
                    # Se a regra do banco encontrou um ID canônico, use-o
                    # Caso contrário, use o texto bruto normalizado.
                    clean_name = ent.ent_id_ if ent.ent_id_ else ent.text.strip().title()

                    # Barreira de Data Quality: Evita ruídos de caracteres soltos ou anomalias gigantes
                    if 2 < len(clean_name) < 150:
                        entity_type = cast(Literal["PER", "ORG", "LOC"], ent.label_)
                        key = (clean_name, entity_type)

                        if key not in seen_keys:
                            seen_keys.add(key)
                            entities_found.append(ArchiveEntityDTO(name=clean_name, entity_type=entity_type))
            # Adiciona a lista de entidades validadas deste documento ao resultado final
            results.append(entities_found)

        return results

    def lemmatize(self, text: str, stopwords: list[str]) -> list[str]:
        doc = self.nlp(text.lower())
        lemmas = []

        for token in doc:
            # Só aceita palavras que: não são pontuação, não são espaços, e não são stopwords

            if token.is_punct or token.is_space or token.like_num:
                continue

            lemma = token.lemma_
            # Ignora stopwords, tokens classificados como stop pelo spaCy e palavras de 1 letra (como 'º' ou 'a')
            if lemma not in stopwords and not token.is_stop and len(lemma) > 2:
                lemmas.append(lemma)

        return lemmas
