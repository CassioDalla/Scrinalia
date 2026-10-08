# Additional terms under section 7 of the GNU AGPL v3

The Program is licensed under the **GNU Affero General Public License, version 3**
([`LICENSE`](LICENSE)) — `AGPL-3.0-only` — together with the additional term stated below.
This term is added under section 7 of that license, which expressly permits it. It is an
attribution requirement and **not** a further restriction within the meaning of section 10:
it adds no restriction on any field of use, on charging for the software, or on the rights
the license already grants.

## 1. Preservation of the author attribution — section 7(b)

Section 7(b) of the GNU AGPL v3 permits:

> "Requiring preservation of specified reasonable legal notices or author attributions in
> that material or in the Appropriate Legal Notices displayed by works containing it"

Exercising that permission, the attribution that must be preserved is the one the Program
displays in its footer, and it consists of these four elements:

1. the **copyright notice naming the original author** of the Program;
2. the name of the **license** the work is released under;
3. a **link to that license**; and
4. a **link to the Corresponding Source** of the work.

The concrete wording the Program itself displays is defined once, in
[`apps/curator/src/lib/attribution.ts`](apps/curator/src/lib/attribution.ts), and rendered by
the application shell.

**Obligation.** Any work that contains or is based on the Program — including a modified
version — must display all four elements above in the Appropriate Legal Notices it displays.
"Appropriate Legal Notices" has the meaning given in section 0 of the license: a convenient
and prominently visible feature. For a work with a web interface, that means **every page a
user can reach, in the page footer**, and the footer must be reachable without authenticating.

**Scope of the obligation.** These elements must not be removed, obscured, or made less
prominent than they are in the Program, and they must name the **original author** — adding
the modifier's own copyright notice alongside them is expected and permitted, but it does not
replace them.

## 2. Marking modified versions

No additional term is added for this. Section 5(a) of the license already requires that a
modified version "carry prominent notices stating that you modified it, and giving a relevant
date", and section 5(b) already requires that it state that it is released under this license
and any conditions added under section 7.

## 3. What this term deliberately does not require

To keep the term within what section 7 permits, and because these things are not enforceable
by a license, none of the following is a condition of this license:

- contributing modifications back to this project or to any particular place;
- publishing modifications anywhere the license does not already require (see section 13 of
  the license for the network case);
- refraining from charging money for the software, or from operating it as a service;
- any restriction on the field of use.

Publishing improvements back is asked for, not required: the request is made in prose in
[`README.md`](README.md), where a request belongs, and not here, where it would be
unenforceable.

## 4. Notice

Per section 7 of the license — *"you must place, in the relevant source files, a statement of
the additional terms that apply to those files, or a notice indicating where to find the
applicable terms"* — this file **is** that notice. It is referenced by [`README.md`](README.md)
and by the license metadata in `pyproject.toml` and `package.json`.
