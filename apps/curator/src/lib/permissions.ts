import type { AuthUser } from "@/api/client";

/**
 * The four areas a request can write to, mirroring the server's `Permission`.
 *
 * A mirror, and a deliberately one-way one: it exists so the shell can **hide** a screen an account
 * cannot work in, and it never decides anything. The API is the authority — every route declares its
 * own permission and answers 403 with a sentence — so if the two maps ever disagree, the server wins
 * and the screen shows the refusal. What this map must never do is *grant* something: a wrong entry
 * here can only make the menu more optimistic, never make the API accept a request.
 */
export type Permission = "CURATE" | "CATALOGUE" | "OPERATE" | "ADMIN";

/**
 * What each role carries beyond reading — the twin of `ROLE_PERMISSIONS` in
 * `src/scrinalia/domains/identity/domain/permissions.py`.
 *
 * Reading is not in here on purpose, on both sides: reading is what an authenticated session is.
 * The three roles differ in what they can *change* — a viewer consults the collection, a curator
 * decides about descriptions and catalogues, and the administrator owns the installation (accounts
 * and the AI workers).
 */
const ROLE_PERMISSIONS: Record<AuthUser["role"], readonly Permission[]> = {
  ADMIN: ["CURATE", "CATALOGUE", "OPERATE", "ADMIN"],
  CURATOR: ["CURATE", "CATALOGUE"],
  VIEWER: [],
};

/** Whether the account may work in that area. Deny by default, like the server. */
export function can(role: AuthUser["role"], permission: Permission): boolean {
  return ROLE_PERMISSIONS[role].includes(permission);
}

/** How the role reads to the person holding it. Kept beside the map so the two move together. */
export const ROLE_LABEL: Record<AuthUser["role"], string> = {
  ADMIN: "Administrador",
  CURATOR: "Curador",
  VIEWER: "Leitor",
};

/** The roles a select offers, in the order of most to least reach. */
export const ROLES: AuthUser["role"][] = ["ADMIN", "CURATOR", "VIEWER"];
