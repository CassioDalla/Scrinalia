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
  system: {
    runStatus: {
      QUEUED: "Queued",
      RUNNING: "Running",
      SUCCESS: "Succeeded",
      FAILED: "Failed",
      INTERRUPTED: "Interrupted",
      CANCELLED: "Cancelled",
    },
    failureSource: { WORKER: "worker run", API: "request" },
    trigger: { API: "panel", CLI: "command line", SCHEDULE: "schedule" },
    unit: {
      origin: "origins",
      staging: "imported records",
      document: "descriptions",
      tag: "tags",
      pair: "pairs",
    },
    noModel: "no model",
    batch: "batch {size}",
    dimensions: "{count} dimensions",
    stepsOff: "with steps disabled",
    noParameters: "no parameters",
    optionsNotRecorded: "options not recorded in this run",
    optionsExample: 'Pass the options as a JSON object, for example {"force": true}.',
    invalidJson: "Invalid JSON.",
  },
  queues: {
    hierarchy_orphans: {
      label: "Unmaterialised arrangement",
      description: "Descriptions the arrangement cannot place in a chain yet.",
    },
    hierarchy_plans: {
      label: "Levels awaiting a decision",
      description: "Levels proposed by reading the reference codes.",
    },
    tag_merge_proposals: {
      label: "Tag merge proposals",
      description: "Tags with similar spellings awaiting the merge decision.",
    },
    cross_domain_conflicts: {
      label: "Subject and entity conflicts",
      description: "Terms that collide: the same name is a subject and a proper name.",
    },
    subject_low_confidence: {
      label: "Subject with low confidence",
      description: "Tags the classifier was not confident enough to file in a category.",
    },
    orphan_subject_tags: {
      label: "Tags without a subject category",
      description: "Tags without a category: no subject badge can be shown for them.",
    },
    typology_low_confidence: {
      label: "Typology with low confidence",
      description: "Descriptions whose typology the classifier could not decide.",
    },
    anomalies: {
      label: "Detected anomalies",
      description: "Descriptions the quality validator flagged.",
    },
    unreviewed_documents: {
      label: "Unreviewed descriptions",
      description: "Descriptions no person has reviewed yet.",
    },
  },
  vocabulary: {
    termKind: {
      DISTRICT: {
        label: "Neighbourhood",
        hint: "A neighbourhood: the finest place the collection distinguishes. The entity axis carries it.",
      },
      MUNICIPALITY: {
        label: "Municipality",
        hint: "A municipality, including a foreign city. The entity axis carries it.",
      },
      STATE: { label: "State", hint: "A state or province. The entity axis carries it." },
      REGION: {
        label: "Region",
        hint: "A region broader than a municipality. The entity axis carries it.",
      },
      COUNTRY: {
        label: "Country",
        hint: "A country the collection's records reach. The entity axis carries it.",
      },
      PERSON: {
        label: "Person",
        hint: "A person's name: the producer or the person depicted, never a subject.",
      },
    },
  },
  entities: {
    type: {
      PER: { label: "Person", hint: "People's names, including a document's author." },
      ORG: { label: "Organisation", hint: "Institutions, companies and producing bodies." },
      LOC: { label: "Place", hint: "Places: streets, neighbourhoods, rivers and buildings." },
    },
    origin: {
      HUMAN: { label: "confirmed", hint: "A person associated or confirmed this entity." },
      AI: {
        label: "AI",
        hint: "The extractor proposed this entity and nobody has reviewed it yet.",
      },
      UNKNOWN: {
        label: "not traced",
        hint: "Link written before the system recorded who created it: it cannot be attributed to anyone.",
      },
    },
    mergeFlag: {
      MEMBER_WITH_DIGITS: {
        label: "member with digits",
        hint: "A member has a number in its name. It may be the same name with and without the number, or another name: the number does not decide.",
      },
      MIXED_TYPES: {
        label: "different types",
        hint: "A member has a type different from the canonical one. Absorbed spellings start resolving with the canonical type.",
      },
      MEMBER_IS_SYNONYM: {
        label: "member is an absorbed spelling",
        hint: "A member is a spelling already absorbed by an earlier merge — the grouping may reflect an old decision.",
      },
      ORPHAN_MEMBER: {
        label: "member without a description",
        hint: "A member is not linked to any description. Absorbing it loses no link, but it is the kind of record the orphan purge deletes.",
      },
    },
    exclusionSource: {
      JUDGE: {
        label: "conflict judge",
        hint: "The conflict judge concluded the spelling belongs to the subject axis, not to proper names.",
      },
      HUMAN: {
        label: "curation",
        hint: "An archivist decided the term is a subject; the tag that justifies the decision is recorded.",
      },
    },
    conflictWinner: {
      TAG: { label: "the subject (tag)", hint: "The spelling is a subject. The term enters the entity exclusions with the tag that justifies it, and the extractor stops returning it as a proper name." },
      ENTITY: { label: "the entity", hint: "The spelling is a proper name. The tag's name is banned from the subject axis, and that tag's classification is lost." },
    },
  },
  csv: {
    parse: {
      unclosedQuote: "One of the fields has an unclosed quote.",
      empty: "The file has nothing to import.",
      headerWithoutName: "One of the header columns has no name.",
    },
    import: {
      headerOnly: "The file has only the header and no data rows.",
      tooManyRows: "The file has {rows} rows and the limit is {limit}. Split the file into parts.",
      missingRequired: "Required columns are missing: {columns}. Download the template to check the column names.",
      duplicateFields: "More than one column fills the same field: {fields}. Leave only one column per field.",
      columnCount: "Row {line} has {cells} columns, but the header has {headers}.",
      idTooLong: "The identifier accepts at most 50 characters.",
      duplicateId: "The identifier already appears on row {line}. Use a different identifier.",
      required: "Field '{label}' is required and is blank.",
      maxLength: "Field '{label}' accepts at most {max} characters.",
      fileTooLarge: "The import is {mb} MB and the limit is {limit} MB. Split the file into parts.",
    },
  },
  format: {
    reviewStatus: {
      PENDING_AI: "Waiting for AI",
      AI_APPROVED: "Approved by AI",
      NEEDS_REVIEW: "Needs review",
      HUMAN_APPROVED: "Reviewed by a person",
      REJECTED: "Rejected",
    },
    noDate: "no date",
    descriptions: { one: "description", other: "descriptions" },
  },
  producers: {
    placeholder: "Type the name or search an entity",
    searching: "Searching entities…",
    empty: "No entity with that fragment",
    failed: "Could not search the entities now.",
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
    language: "Language",
    automatic: "Automatic",
    localeFailed: "Could not save the language.",
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
  errors: {
    requestFailed: "Could not complete the operation (error {status}).",
  },
  actions: {
    save: { label: "Save", pending: "Saving…" },
    create: { label: "Create", pending: "Creating…" },
    remove: { label: "Remove", pending: "Removing…" },
    confirm: { label: "Confirm", pending: "Confirming…" },
    exclude: { label: "Delete", pending: "Deleting…" },
    retire: { label: "Retire", pending: "Retiring…" },
    reactivate: { label: "Reactivate", pending: "Reactivating…" },
    deactivate: { label: "Deactivate", pending: "Deactivating…" },
    run: { label: "Enqueue run", pending: "Enqueuing…" },
    merge: { label: "Merge", pending: "Merging…" },
    rename: { label: "Rename", pending: "Renaming…" },
    apply: { label: "Apply", pending: "Applying…" },
    preview: { label: "Check impact", pending: "Checking…" },
    undo: { label: "Undo", pending: "Undoing…" },
    ban: { label: "Ban", pending: "Banning…" },
    unban: { label: "Unban", pending: "Unbanning…" },
    discard: { label: "Discard", pending: "Discarding…" },
    cancel: { label: "Cancel" },
    close: { label: "Close" },
    recheck: { label: "Check again", pending: "Checking…" },
  },
  digitalObject: {
    label: "Digital object",
    hint: "Attachments (image, PDF, audio) are not uploaded yet; the record keeps the description.",
    disabled: "Unavailable for now",
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
      hint: "What the classification must not guess",
      description:
        "The meaning verdict: the subject classification stops guessing these terms. Confirming here also bans the spelling, but does not remove the Tag from the collection.",
    },
    blockedSpellings: {
      label: "Blocked spellings",
      hint: "What must not become a tag again",
      description:
        "The spellings the extractor must not recreate as tags, on the axis where they were blocked — and the deletion of the tags that already exist with those names.",
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
  spellings: {
    notice:
      "Blocking a spelling stops it from becoming a tag again on the chosen axis and removes nothing from the collection. Blocking is not the same as saying the term is not a subject — what makes the classification stop is {verdict}. Deleting the tags that already exist with those names is under {purge}, below.",
    purgeCard: "Delete the tags with these names",
    verdictDeleteHint: "Deleting the tags is in {blocked}.",
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
