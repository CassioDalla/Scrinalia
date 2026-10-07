# ADR 0006: AGPL-3.0-only, with a preserved author attribution

- **Status:** Accepted
- **Date:** 2026-10-07

## Context

Phase 5 of `TODO.md` listed the license first among the 1.0 blockers, for the plainest possible
reason: there was **no `LICENSE` file at all**, which is not "no license" but the strictest one —
all rights reserved. Nobody could legally use, copy or modify the software, and every one of the
project's goals (another institution installing it, a university extending it, a city archive
forking it) was blocked by a default nobody chose.

The owner stated five requirements, and they do not all point the same way:

| # | Requirement | Legal reading |
| -: | --- | --- |
| R1 | the code cannot be taken closed | copyleft |
| R2 | others using it is fine | freedom to use, study, modify, redistribute |
| R3 | nobody may make money selling it as SaaS | a **restriction on a field of use** |
| R4 | the original author stays in the page footer, always | an **attribution** that must survive forks |
| R5 | third-party modifications must be given back to the community | an obligation to **publish the derivative's source** |

Two facts decide the shape of the answer.

**First, R3 cannot be reconciled with R1/R2 as stated.** Open Source Definition criterion 6 is
explicit: *"The license must not restrict anyone from making use of the program in a specific
field of endeavor."* No OSI-approved license forbids selling, so satisfying R3 requires
abandoning the open-source label — this is a choice between two coherent packages, not a search
for a better-kept license. The requirement is also inverted relative to how network copyleft
works: modifying does not earn the right to monetize, it **triggers** the obligation to publish.
AGPL §4 says outright that a licensee *"may charge any price or no price for each copy that you
convey"*.

**Second, R4 and R5 are already in the AGPL, which is what makes them enforceable at all.**
Verified against the license text:

- **§7(b)** permits adding the term *"requiring preservation of specified reasonable legal
  notices or author attributions in that material or in the Appropriate Legal Notices displayed
  by works containing it"* — this is R4, as a condition that forks inherit. The license also
  **defines** "Appropriate Legal Notices" (section 0) as a conveniently and prominently visible
  feature that displays a copyright notice and how to view the license, and §5(d) requires
  interactive interfaces to display them.
- **§13** requires that *"if you modify the Program, your modified version must prominently offer
  all users interacting with it remotely through a computer network ... an opportunity to receive
  the Corresponding Source of your version"*, and **§5(a)** requires a modified version to
  *"carry prominent notices stating that you modified it, and giving a relevant date"* — this is
  R5, in the enforceable form.

The alternatives were weighed against the sector this system is built for, and against the
dependency stack actually installed.

## Decision

1. **The project is licensed under `AGPL-3.0-only`**, whose verbatim text is `LICENSE`. The
   `-only` form is deliberate: a licensee should not wake up bound by a licence version that did
   not exist when they adopted it.
2. **One additional term is added, under §7(b): the author attribution must be preserved.**
   It is stated in `LICENSE-ADDITIONAL-TERMS.md`, and requires four elements to keep being
   displayed in the Appropriate Legal Notices — the copyright notice naming the original author,
   the license name, a link to the license, and a link to the Corresponding Source — on every
   page a user can reach, without authenticating.
3. **No other condition is added.** Contributing modifications back, refraining from charging for
   the software, and any field-of-use restriction are explicitly **not** conditions, because
   §7 permits additional terms only of certain kinds and declares *"all other non-permissive
   additional terms"* to be further restrictions, which §10 forbids imposing.
4. **The attribution has a single definition in code**: `apps/curator/src/lib/attribution.ts`,
   rendered by `AttributionFooter` through `AppShell` so that every screen shows it without a
   route remembering to. The same constant holds the display name, because the rename is coming.
5. **The license is declared in the metadata as well as the file**: `license` in
   `pyproject.toml`, `package.json` and `apps/curator/package.json`, plus `license-files` so both
   documents ship inside the wheel — verified in the built metadata as
   `License-Expression: AGPL-3.0-only` with both `License-File` entries.
6. **Publishing improvements back is asked for, not required.** R5's "back to the community"
   half is unenforceable by any license — §13 obliges offering source *to the users of that
   deployment*, not filing a pull request upstream. The request is therefore made in prose in
   `README.md`, where it belongs.

## Rationale

- **The attribution requirement is what decides the license.** Under Apache-2.0 a fork may delete
  the footer outright — it must keep the `NOTICE` file and mark modified files (§4), but nothing
  requires a user interface to display anything. The owner asked for the attribution *always*,
  and §7(b) is the only mechanism in the free-software catalogue that delivers "always".
- **Closing the closed-SaaS path is the enforceable half of R3.** A modified deployment must
  offer its Corresponding Source to its users, which is the version of "nobody takes this closed
  and profits" that a license can actually hold. The unmodified-deployment loophole is real and
  is accepted: §13 triggers on modification.
- **The "institutions ban AGPL" objection does not survive contact with this sector.** The
  objection is a large-enterprise phenomenon, and its most explicit statement —
  [Google's AGPL policy](https://opensource.google/documentation/reference/using/agpl-policy) —
  is about blast radius: *"any product or service that depends on AGPL-licensed code ... may be
  subject to the virality of the AGPL license"*, which is existential for a company whose product
  *is* an integrated network service. An archive that installs this system for its own archivists
  has no such radius: the instance is not linked into a proprietary product, it *is* the product.
  Measured with the SPDX license of each (GitHub API, 2026-10-07):

  | System | Domain | License |
  | --- | --- | --- |
  | **AtoM / Access to Memory** | **ISAD(G) archival description — the direct comparable** | **AGPL-3.0** |
  | **Archivematica** | digital preservation, the sector's flagship | **AGPL-3.0** |
  | Heratio | GLAM platform with AI metadata enrichment, commercially developed | AGPL-3.0-or-later |
  | Tainacan | Brazilian digital collections | GPL-3.0 |
  | Omeka · CollectiveAccess · Islandora | GLAM · museums · repositories | GPL-3.0 · GPL-3.0 · GPL-2.0 |
  | ArchivesSpace | archival description | permissive (the outlier) |

  The direct comparable is already AGPL-3.0 and is installed by the national, university and
  municipal archives this system targets. The licence is the sector's norm, not a departure.
- **The stack is compatible — checked, not assumed.** Scanning the installed distributions found
  no GPL or AGPL dependency: `psycopg2` is LGPL (used as a library), `certifi`, `fqdn` and `tqdm`
  are MPL-2.0 (file-scoped), and the remainder is MIT/BSD/Apache-2.0, which is one-way compatible
  into AGPLv3. The AGPL therefore costs nothing technically; any cost is adoption policy.
- **The trademark is what stops branded resale, and it is not part of the licence.** Under any
  code licence the author keeps the name, and §7(e) explicitly permits declining to grant
  trademark rights. "Nobody may offer this as *this project*" is a marking question, not a
  licensing one, and it is why the code licence could be chosen on the closed-fork question alone.
- **The licence text is the verbatim FSF text, and that is checkable.** `gnu.org` is unreachable
  from this environment, so `LICENSE` was taken from SPDX's `license-list-data`, which is a
  byte-exact copy: `sha256 d8a6cc31abc16b6748c7a21f21611f5a1ec33f67d22ca23d7da1c19b95496bee`,
  identical to the upstream file's hash. The licence forbids changing its own text, so this
  matters.

## Consequences

Positive: the software is usable, modifiable and redistributable today; the author's attribution
survives every fork by construction rather than by courtesy; a fork that improves the system and
serves it over a network must publish what it changed; and the whole thing works offline, in a
system another institution installs, which is the stated goal of phase 5.

Negative, and accepted:

- **The realistic failure mode is the outsourced vendor, not the institution.** When a public body
  has no in-house team and tenders the installation, the bidder is a company — and a company may
  hold a blanket AGPL ban. That is the one scenario where this licence costs adoption, and it is
  narrow and checkable. If it materialises, the answer is dual licensing (see the revisit
  trigger), not a rushed relicence.
- **An unmodified deployment owes nothing.** A third party may host this as a service, unmodified,
  and charge for it. §13 does not reach them. This is inherent to AGPL and cannot be added as a
  term, because a field-of-use restriction is exactly what §7 and §10 forbid.
- **A fork may satisfy §13 without ever contributing upstream.** It must offer source to its own
  users; it need not send it anywhere. Anyone may then pull it, which is the community benefit
  actually obtained — worth stating plainly rather than implying a contribution obligation that
  does not exist.
- **The attribution now lives in three places that must agree**: the legal statement in
  `LICENSE-ADDITIONAL-TERMS.md`, the SPDX identifier in `pyproject.toml`/`package.json`, and the
  display text in `apps/curator/src/lib/attribution.ts`. The first states the four required
  elements rather than exact wording, so a rename changes the code and not the legal term — but a
  reviewer changing one is obliged to check the others.
- **A §7 notice is not placed as a header in every source file.** §7 allows either a statement in
  the relevant files *or* a notice of where to find the terms; this takes the second branch, in
  `README.md` plus the metadata fields. Adding 220 file headers would also collide with the
  rename commit, which touches the same files for a different reason.

## Alternatives considered

- **Apache-2.0** (what `TODO.md` had recommended). Maximum institutional adoption and an explicit
  patent grant, and the safest choice if adoption friction were the only consideration. Rejected
  because it delivers none of R3, R4 or R5: a fork may close the code, and the footer may be
  deleted. It remains the right answer if a named adopter's vendor turns out to ban AGPL.
- **`AGPL-3.0-or-later`.** Rejected: predictability for the licensee outweighs the option of
  following a future FSF version. Section 13's second paragraph already permits combining with
  GPLv3 works, which is the compatibility that was actually needed.
- **GPL-3.0.** Rejected: it has no network clause, so a hosted fork never has to publish — R5
  disappears entirely.
- **FSL-1.1-ALv2** (or BSL 1.1). These genuinely forbid competing use and convert to Apache-2.0
  after two (or at most four) years per version, which is the closest thing to R3 that exists.
  Rejected because they are not open source — FSL's own FAQ says so — and, decisively for this
  decision, they carry no attribution clause, so R4 would degrade from a condition to a
  convention. Trading enforceable attribution for a SaaS ban was the wrong trade here.
- **Commons Clause over Apache-2.0.** Rejected on two grounds. It does not do what it appears to:
  its FAQ states plainly that *"Is this 'Open Source'? **No.**"* and that offering a value-added
  product as SaaS is *permitted*. And it is incoherent with AGPL — §7 declares non-permissive
  additional terms to be further restrictions, and §10 forbids imposing them — so the two
  families are mutually exclusive rather than combinable.
- **Dual licensing from the start** (AGPL plus a commercial option). Attractive as a pressure
  valve, and it remains the plan if a vendor is blocked. Not adopted now because it requires
  holding copyright on every contribution, which means a CLA — and a CLA should be introduced
  *before* the first outside contribution lands, not retrofitted over one.

## Revisit trigger

Reconsider when a **named** prospective adopter — or the vendor it contracts — reports a policy
that forbids AGPL. The response is dual licensing: keep AGPL for everyone and grant a commercial
licence case by case, which is what the Commons Clause was trying to approximate and what the
sector's commercially developed AGPL projects do. That requires a CLA or DCO, so if outside
contributions are expected before then, introduce it first. A second trigger: if the project is
ever submitted to a public software programme whose rules require a specific licence family,
check that requirement against this decision before submitting.
