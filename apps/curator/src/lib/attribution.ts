/**
 * Who wrote this, and under what terms.
 *
 * These are the four elements section 7(b) of the AGPL requires a modified version to keep
 * displaying (see `LICENSE-ADDITIONAL-TERMS.md`): the author, the license, a link to it, and a
 * link to the source. They live here, in one place, for the same reason the level ladder and the
 * typologies live in the database — a second copy in a component is a second thing to forget.
 *
 * Two of these are load-bearing beyond the footer:
 *
 * - `sourceUrl` is also the offer of Corresponding Source that section 13 of the license requires
 *   of a modified deployment serving users over a network, so it must stay a real address.
 * - `name` is the project's display name; renaming the project is a change to this line, not to
 *   every screen that prints it.
 */
export const ATTRIBUTION = {
  /** The display name of the project. */
  name: "Memória Curitibana",
  /** The original author, as named in the copyright notice the license requires be preserved. */
  author: "CassioDalla",
  /** Year of first publication, for the copyright notice. */
  year: "2026",
  /**
   * SPDX identifier. Identical to `license` in `pyproject.toml` and in both `package.json`
   * files — if one changes, all of them change together.
   */
  license: "AGPL-3.0-only",
  /** Where the license text can be read. */
  licenseUrl: "https://www.gnu.org/licenses/agpl-3.0.html",
  /** The public repository: the Corresponding Source this work offers. */
  sourceUrl: "https://github.com/CassioDalla/memoria-curitibana-etl",
} as const;
