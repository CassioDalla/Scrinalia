/**
 * The English catalogue: typed as the Portuguese one, so a missing or extra message fails `tsc`
 * (ADR 0020 §1).
 */

import { ATTRIBUTION } from "@/lib/attribution";

import type { pt } from "./pt";

export const en: typeof pt = {
  product: {
    tagline: "Collection curation",
    documentTitle: `${ATTRIBUTION.name} — Curation`,
  },
  format: {
    noDate: "no date",
    descriptions: { one: "description", other: "descriptions" },
  },
  notFound: {
    title: "Screen not found",
    hint: "The address does not match any screen in the system.",
    backHome: "Back to the home",
  },
  attribution: {
    license: "License",
    source: "Source code",
    version: "Installation version",
  },
  roles: {
    ADMIN: "Administrator",
    CURATOR: "Curator",
    VIEWER: "Viewer",
  },
  shell: {
    expandMenu: "Expand the menu",
    collapseMenu: "Collapse the menu",
    mainMenu: "Main menu",
    changePassword: "Change password",
    close: "Close",
    signOut: "Sign out",
    signingOut: "Signing out…",
  },
  nav: {
    sections: {
      acervo: "Collection",
      assuntos: "Subjects",
      entidades: "Entities",
      qualidade: "Quality",
    },
  },
  settingsTabs: {
    arranjo: "Arrangement and catalogues",
    operacao: "Operation",
    acesso: "Access",
  },
  screens: {
    inbox: {
      label: "Home",
      hint: "What needs me today",
      description: "Each card leads to the screen that resolves the pending work, already filtered.",
    },
    collection: {
      label: "List and Search",
      hint: "Facets and Filters",
      description: "Search the collection by keyword, by meaning or with a combined search.",
    },
    tree: {
      label: "Tree",
      hint: "Collection hierarchy",
      description:
        "Browse the materialised arrangement. Choosing a node shows the branch and the descriptions it holds.",
    },
    deletions: {
      label: "Deletion history",
      hint: "Record of removed items",
      description:
        "Look up the original data of permanently deleted records, kept for history and audit only.",
    },
    diagnostics: {
      label: "Arrangement diagnostics",
      hint: "Where it is inconsistent",
      description:
        "Where the collection is inconsistent. Nothing is corrected on its own: each row shows the evidence and leads to where the decision is made.",
    },
    tags: {
      label: "Tags",
      hint: "Use, duplicate terms, merge",
      description: "Manage the relevance of the tags, find duplicates and merge similar terms.",
    },
    categories: {
      label: "Categories",
      hint: "Organisation of subjects",
    },
    discover: {
      label: "Discover categories",
      hint: "Groups by theme",
      description: "Groups the vocabulary by theme to find the subject that has not been classified yet.",
    },
    subjectExclusions: {
      label: "Not a Subject",
      hint: "What the rule does not consider",
      description:
        "The terms the subject classification must not guess. Marking does not delete the tag — it stays in the collection and reachable by search — but bans the spelling from becoming a tag again.",
    },
    entities: {
      label: "Named Entities (NER)",
      hint: "Relevance, type and merge",
      description:
        "Review the relevance of the terms, set the category (person, place or institution) and join repeated names.",
    },
    nerExclusions: {
      label: "Remove from Entities",
      hint: "This is a subject, not a name",
      description: "Classify as a thematic term (subject) instead of a person, place or collective entity.",
    },
    conflicts: {
      label: "Conflicts",
      hint: "Subject x proper name",
    },
    textTemplates: {
      label: "Excerpts",
      hint: "Boilerplate and scope",
    },
    cleaningRules: {
      label: "Rules",
      hint: "Rewrite or flag",
    },
    anomalies: {
      label: "Anomalies",
      hint: "What the validator flagged",
    },
    plan: {
      label: "Arrangement plan",
      hint: "Decide the levels",
    },
    levels: {
      label: "Description levels",
      hint: "The NOBRADE ladder",
    },
    typologies: {
      label: "Typologies",
      hint: "The diplomatic form",
    },
    vocabulary: {
      label: "Collection vocabulary",
      hint: "Names and places of this collection",
    },
    workers: {
      label: "Workers and runs",
      hint: "What runs and what ran",
      description:
        "The panel of what is running now — preset, model, queue, last and active run — and the history of what already ran, in the tab beside.",
    },
    origins: {
      label: "Origins",
      hint: "Configure, pause and schedule",
      description:
        "The sources this installation reads, with each one's queue, schedule and configuration; manual entry and CSV import live in the Collection, under New Description.",
    },
    newDescription: {
      label: "New Description",
      hint: "Type or import CSV",
      description: "Create a description manually or import a CSV.",
    },
    workerSettings: {
      label: "Worker configuration",
      hint: "Engine, preset and the history",
      description:
        "The saved default of each worker — engine, preset, batch and options — and who changed what, run after run.",
    },
    health: {
      label: "System health",
      hint: "Database, models, storage and origins",
      description:
        "Database, Ollama models, thumbnail storage, ingestion origins and the process's effective configuration.",
    },
    settings: {
      label: "Settings",
      hint: "Accounts, catalogues and operation",
      description: "The screens decided once, away from the day-to-day curation.",
    },
    users: {
      label: "Users",
      hint: "Accounts, roles and sessions",
    },
    dossier: {
      label: "Description",
      hint: "The dossier of one description",
    },
  },
  auth: {
    login: {
      email: "E-mail",
      password: "Password",
      signIn: "Sign in",
      signingIn: "Signing in…",
      failure: "Could not sign in.",
      forgot: "I forgot my password",
      noMessage:
        "No message is sent from this screen. An administrator resets your password in {settings}, on the right account.",
      settingsPath: "Settings → Users",
      lastAdmin:
        "If this is the last active administrator account and nobody can sign in, access is restored from the server terminal by whoever operates the machine (operations guide).",
    },
    setup: {
      title: "First access to the installation",
      explanation:
        "This installation has no accounts yet, and the administration account can only be created once. It administers the system and creates the others in Settings › Users.",
      email: "E-mail",
      name: "Name",
      password: "Password",
      confirmation: "Confirm the password",
      mismatch: "The two passwords do not match.",
      failure: "Could not create the account.",
      create: "Create account",
      creating: "Creating…",
      noRecovery:
        "There is no password recovery by e-mail: keep this password. If it is lost, only whoever administers the installation can set another.",
    },
    password: {
      title: "Change password",
      forced: "This account still uses the temporary first-access password. Choose your own password to continue.",
      voluntary: "The account's other sessions will be ended.",
      current: "Current password",
      next: "New password",
      confirmation: "Confirm the new password",
      mismatch: "The two passwords do not match.",
      failure: "Could not change the password.",
      changing: "Changing…",
      change: "Change password",
      cancel: "Cancel",
    },
  },
};
