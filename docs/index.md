# Scrinalia

Scrinalia catalogues and manages archival descriptions (ISAD(G) metadata). It ingests records from
an origin, cleans and structures them, enriches them with AI (named-entity recognition, zero-shot
typology classification, subject macro-categories, embeddings) and puts every result under a
human-in-the-loop review: the machine proposes, an archivist decides, and the decision is recorded.

An institution installs it. There is no hosted service behind it: the database, the object storage
and the language model run where the collection lives, and the system works offline (ADR 0005).

## How the pieces fit

Three layers, each a domain under `src/scrinalia/domains/`:

| Layer | Holds |
| --- | --- |
| `ingestion` | the scraping queue: what was found at the origin and what is waiting to be read |
| `staging` | the parsed, cleaned, structured record — before any AI or human decision |
| `archive` | the final description: ISAD(G) fields, AI enrichment, review status, diffusion |

A fourth domain, `identity`, is not a layer of that pipeline: it owns the accounts, the sessions and
the role map (ADR 0009).

The archivist works in a React SPA served by the API itself, so a deployment is one origin and has
no CORS rule to get wrong (ADR 0003). Every screen reads and writes through the generated client of
the OpenAPI contract, which is committed and whose staleness fails the build.

## Guides

| Guide | Read it to |
| --- | --- |
| [Installation and deployment](guides/install.md) | install the system, configure it, put it behind HTTPS and back it up |
| [Operations](guides/operate.md) | run and re-run the workers, read the panel, the run ledger and the failure groups |
| [Curation](guides/curate.md) | know what each screen decides, and which decisions have no way back |
| [Data model](guides/data-model.md) | understand what the tables mean, the idempotency stamps and the ledgers |

The fastest path from a fresh clone to a running system is in the
[`README.md`](https://github.com/CassioDalla/Scrinalia#getting-started). The conventions and the
architectural traps are in
[`AGENTS.md`](https://github.com/CassioDalla/Scrinalia/blob/main/AGENTS.md), and the work that is left
in the [open issues](https://github.com/CassioDalla/Scrinalia/issues) and their milestones.

## Decisions and status

The [architecture decisions](adr/index.md) explain why the system is built the way it is, including
the alternatives that were measured and rejected. **Scrinalia is at 1.1**: the pipeline, the AI
workers, the review governance, the authentication and the curator surface are complete, and the
public diffusion surface exists with no site in front of it yet. The
[open issues](https://github.com/CassioDalla/Scrinalia/issues) carry the work that is left, the limits
accepted on purpose are in the
[operations guide](guides/operate.md#known-limits-and-accepted-trade-offs), and the
[documentation log](log.md) records what was reviewed and when.

## License

`AGPL-3.0-only`, plus one additional term under section 7(b) of that license requiring the author
attribution to be preserved. A modified version offered over a network must publish its source. The
decision and its consequences are in [ADR 0006](adr/0006-license-and-author-attribution.md).
