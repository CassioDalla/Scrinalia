---
translation_of: index.md
---

# Scrinalia

O Scrinalia cataloga e gerencia descrições arquivísticas (metadados ISAD(G)). Ele ingere registros
de uma origem, limpa e estrutura esses registros, enriquece o acervo com IA (reconhecimento de
entidades nomeadas, classificação de tipologia por zero-shot, macro categorias de assunto,
embeddings) e coloca todo resultado sob revisão humana: a máquina propõe, o arquivista decide, e a
decisão fica registrada.

Quem instala é a instituição. Não existe serviço hospedado por trás: o banco de dados, o
armazenamento de objetos e o modelo de linguagem rodam onde o acervo está, e o sistema funciona
offline (ADR 0005).

## Como as peças se encaixam

Três camadas, cada uma um domínio em `src/scrinalia/domains/`:

| Camada | O que guarda |
| --- | --- |
| `ingestion` | a fila de coleta: o que foi encontrado na origem e o que falta ler |
| `staging` | o registro interpretado, limpo e estruturado — antes de qualquer decisão de IA ou humana |
| `archive` | a descrição final: campos ISAD(G), enriquecimento de IA, situação de revisão e difusão |

Um quarto domínio, `identity`, não é camada desse pipeline: ele é dono das contas, das sessões e do
mapa de papéis (ADR 0009).

O arquivista trabalha numa SPA em React servida pela própria API, então a implantação é uma origem
só e não há regra de CORS para errar (ADR 0003). Toda tela lê e escreve pelo cliente gerado do
contrato OpenAPI, que é commitado e cuja defasagem quebra o build.

## Guias

| Guia | Leia para |
| --- | --- |
| [Instalação e implantação](guides/install.md) | instalar o sistema, configurá-lo, colocá-lo atrás de HTTPS e fazer backup |
| [Operação](guides/operate.md) | rodar e reprocessar os workers, ler o painel, o ledger de execuções e os grupos de falha |
| [Curadoria](guides/curate.md) | saber o que cada tela decide e quais decisões não têm volta |
| [Modelo de dados](guides/data-model.md) | entender o que as tabelas significam, os carimbos de idempotência e os ledgers |

O caminho mais curto de um clone novo até o sistema rodando está no
[`README.md`](https://github.com/CassioDalla/Scrinalia#getting-started). As convenções e as
armadilhas de arquitetura estão no
[`AGENTS.md`](https://github.com/CassioDalla/Scrinalia/blob/main/AGENTS.md), e o roteiro no
[`TODO.md`](https://github.com/CassioDalla/Scrinalia/blob/main/TODO.md).

## Decisões e situação

As [decisões de arquitetura](adr/index.md) explicam por que o sistema é como é, incluindo as
alternativas que foram medidas e descartadas. **O Scrinalia está na 1.0**: o pipeline, os workers de
IA, a governança da revisão, a autenticação e a superfície de curadoria estão completos, e a
superfície de difusão pública existe sem site na frente dela ainda. O `TODO.md` carrega o estado
atual, e o [registro da documentação](log.md) registra o que foi revisado e quando.

## Licença

`AGPL-3.0-only`, mais um termo adicional do §7(b) dessa licença exigindo que a atribuição de autoria
seja preservada. Uma versão modificada oferecida por rede precisa publicar o seu código-fonte. A
decisão e as suas consequências estão no [ADR 0006](adr/0006-license-and-author-attribution.md).
