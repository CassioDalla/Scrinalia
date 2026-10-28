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
  common: {
    nothingFound: "Nothing found",
    readingDescriptions: "Reading the descriptions…",
    next: "Next →",
    previous: "← Previous",
    range: "{from}–{to} of {total}",
    readingDescription: "Reading the description…",
    edit: "Edit",
    close: "close",
    closeAction: "Close",
    notInformed: "— not informed —",
  },
  pages: {
    anomalies: {
      fixHint:
        "Corrigir é revisar a ficha: a edição fica no histórico e marca a descrição como revisada por humano; a partir daí a IA não a sobrescreve.",
      status: "{count} descriptions with an anomaly",
      reasonHint: "Reason recorded by the quality validator",
      rules: "Rules",
    },
    inbox: {
      notReadyTitle: "This screen is not ready for use yet.",
      notReady: "screen in preparation",
      empty: "nothing pending",
      open: "open →",
      emptyTitle: "No pending item received",
      emptyHint: "Nothing arrived, which does not mean the collection is in order. Tell whoever administers the installation.",
    },
    settings: {
      emptyTitle: "Nothing to configure",
      emptyHint:
        "The cards on this page are the installation's configuration screens (accounts, catalogues, arrangement and operation), and your role reaches none of them. That is why the Settings entry does not appear in the menu.",
    },
    newDescription: {
      typeTab: "Type",
      csvTab: "Import CSV",
      noCategory: "no category",
      accessPlaceholder: "Search a tag or type a new term",
      accessAdd: "Add “{term}”",
      accessRemove: "Remove {name}",
      accessSearching: "Searching…",
      accessSearchFailed: "Could not search the catalogue. Press Enter to use the typed term.",
      accessDuplicate: "“{term}” is already in the list.",
      accessPreviewFailed: "Could not check the access points; they will be sent as typed.",
      dropped: "“{label}” {reason} and will be discarded.",
      reasonStopword: "is a blocked term",
      reasonTooShort: "is too short (minimum 3 characters)",
      reasonTooLong: "is too long (maximum 100 characters)",
      createdOne: "“{label}” will be created when archived.",
      createdMany: "Will be created when archived: {labels}.",
      synonym: "“{input}” will be linked to “{name}”.",
      respelled: "“{input}” is already in the catalogue as “{name}”.",
      notAllowed: "Your account cannot create descriptions. Ask a curator or an installation administrator.",
      dateRecorded: "Date recorded: {date}.",
      dateRecordedWithSource: "Date recorded: {date} — as in the source: “{expr}”.",
      pendingNote:
        "The record appears in the collection when the transfer runs. Until then, the dossier may still answer “not found”.",
      openDossier: "Open the dossier",
      createBlank: "Create another blank one",
      titleLabel: "Title",
      requiredHint: "Required field.",
      levelLabel: "Description Level",
      unclassified: "— unclassified —",
      parentLabel: "Parent / Higher Unit",
      parentHint: "Select the code of the unit this one belongs to.",
      parentPlaceholder: "BR PRADAP SMU",
      needsParent:
        "The level “{level}” requires a parent unit. You can still save it: the record enters pending and the link is made on the dossier's Arrangement tab.",
      filled: "{count} filled",
      openArea: "Open the area",
      accessSection: "Access Points",
      accessHintShort: "The subjects that became tags in the collection.",
      accessLabel: "Access Points",
      accessFieldHint:
        "Choose tags from the catalogue or type new terms. New terms become tags when the description is archived.",
      sourceUrlLabel: "Source URL",
      sourceUrlHint: "Page where the record came from, when there is one.",
      imageUrlLabel: "Image URL",
      imageUrlHint:
        "If the image is already published elsewhere, the copy into the collection is made automatically.",
      titleMissing: "The title is missing.",
      formId: "form id: {id}",
    },
    origins: {
      statusNone: "No origin configured",
      statusOne: "{count} origin configured · {active} active",
      statusMany: "{count} origins configured · {active} active",
      intro:
        "Ingestion reads the origin, stores the record raw and leaves it structured, ready for transfer. Each origin has its own queue, agenda and configuration.",
      originsTitle: "Origins",
      originsHint:
        "The sources this installation reads: add an available origin, configure it, schedule it, pause it and enqueue a run.",
      addOrigin: "Add origin",
      emptyTitle: "No origin configured",
      emptyHint:
        "The installation does not read any site yet. Add an available origin; the manual entry and the CSV import live in the Collection, under New Description.",
      allConfigured: "All available origins are already configured.",
      entriesTitle: "Entries",
      entriesHint:
        "The manual entry and the CSV import are not reading origins: the record is created in the Collection, and these rows only show each one's state.",
      kindManual: "manual",
      kindCsv: "csv",
      kindSite: "site",
      configure: "Configure",
      scheduleTab: "Agenda",
      viewDetails: "See queue, run and configuration",
      queue: "Queue",
      queueHint: "What this origin's next run will read.",
      processed: "Processed",
      failedCount: "{count} with a fatal error",
      noFatal: "no fatal error",
      lastRun: "Last run",
      none: "none",
      schedule: "Agenda",
      nextRun: "{tz} · next {when}",
      noSchedule: "no schedule",
      operatorOnly: "Configuration, agenda and runs belong to the operator.",
      running: "running",
      queueWillRun: "the queue will move",
      queueWillWait: "the queue will wait",
      activeBadge: "active",
      pausedBadge: "paused",
      noOwnConfig: "No configuration of its own: the origin uses the installation's values when they exist.",
      saving: "Saving…",
      pause: "Pause",
      reactivate: "Reactivate",
      pausedOrigin: "Origin paused",
      alreadyRunning: "A run is already in progress",
      enqueuing: "Enqueuing…",
      enqueueRun: "Enqueue run",
      queuedLine: "Run #{id} in the queue; it has not started yet.",
      noConfigFields: "This origin has no configuration fields.",
      scheduledOptions: "Scheduled run options",
      saveConfig: "Save configuration",
      configSaved: "Configuration saved.",
      cronHint:
        "Five fields (minute, hour, day of month, month, day of week), evaluated in the given time zone. A period that arrives while an ingestion is running is skipped, not enqueued.",
      scheduleField: "Schedule",
      timezoneField: "Time Zone",
      saveSchedule: "Save agenda",
      removeSchedule: "Remove agenda",
      notConfigurable: "not configurable",
      awaitingTransfer: "{count} awaiting transfer.",
      openEntry: "Open the entry",
      addTitle: "Add origin",
      addHint: "Choose an origin that is not configured yet.",
      addNote: "The origin ships with the system; adding it here only activates it in this installation.",
      allAddedTitle: "All origins are already configured",
      allAddedHint: "There is no other reading origin to add.",
      adding: "Adding…",
      add: "Add",
    },
    textTemplates: {
      statusEmpty: "No excerpt in the current filter",
      statusCount: "{count} excerpts in the current filter",
      notice:
        "The scope is the decision that matters. Each excerpt says which text it leaves — vector, name extraction or suggested title. Approving everything the machine suggested made the search results worse: the title prefix helped the title and hurt the vector. That is why there is no approve-all button here.",
      searchTrigger: "+ Find excerpts",
      searchToggle: "Find repeated excerpts",
      searchHint:
        "The sweep looks for repeated blocks in the collection and records each one as a suggestion, without touching the documents.",
      scanHint:
        "The sweep records the candidates as inactive suggestions: nothing changes in the documents before you approve a scope.",
      minRatio: "Minimum Share of the Collection",
      minDocuments: "Minimum Documents",
      scanning: "Scanning…",
      search: "Find",
      scannedLine: "{scanned} documents read · {persisted} candidates recorded.",
      allStatuses: "All",
      emptyTitle: "No excerpt in this filter",
      emptyHint:
        "Run the search above, or write an excerpt by hand. Excerpts appear here according to the chosen filter.",
      documentsBadgeTitle: "Documents where the excerpt appears",
      machineSuggested: "suggested by the machine",
      humanWritten: "written by a human",
      inactive: "inactive",
      variants: "spellings: {list}",
      removeFrom: "Remove from:",
      saveScope: "Save scope",
      approve: "Approve",
      reject: "Reject",
      removeTitle: "Removes from the catalogue and returns the affected documents to the queue",
      requeued: "{count} documents returned to the queue.",
      previewSummary: "{affected} of {scanned} documents would change.",
      newTrigger: "+ Write excerpt",
      newToggle: "Write an excerpt",
      newHint: "Creating the excerpt applies it to the documents; the affected ones return to the queue.",
      newExplain:
        "Creating the excerpt applies it, and the affected documents return to the queue. That is why the create button only enables after checking the impact.",
      textPlaceholder: "exact excerpt, as it appears in the documents",
      actionField: "What to Do with It",
      replaceWith: "Replace with",
      replacementPlaceholder: "text that stays in its place",
      createApply: "Create and apply",
      queued: "{count} documents in the queue.",
    },
    vocabulary: {
      status: "{arrangement} arrangement names · {terms} collection terms ({active} active)",
      notice:
        "These two lists are collection data, not system rules. What belongs to the Portuguese language — rua, avenida, não identificado, 303 anos, a loose year — is not this curation's decision and does not appear here: changing it would change the meaning the system gives the word. Retiring a term does not delete it: it stops being refused and can be suggested as a subject again in the next classification.",
      arrangementSection: "Arrangement vocabulary",
      arrangementHint:
        "The name the arrangement proposal suggests for a level of the reference code. The whole code takes precedence over the last segment: BR PRADAP can have its own name and SMU the secretariat's.",
      collectionSection: "Collection terms",
      collectionHint:
        "What the collection carries and is not a subject. A place remains reachable through search, as an entity of type Place; a person's name is the producer or the person depicted, never a subject. That difference is what the type records.",
      editName: "Edit this name",
      retireName: "The proposal stops suggesting this name.",
      reactivateName: "The proposal suggests this name again.",
      suggestedName: "Suggested Name",
      newName: "+ New name",
      createArrangement: "Create an arrangement name",
      segmentHint: "A code segment (SMU) or the whole code (BR PRADAP).",
      segmentField: "Segment or Code",
      segmentPlaceholder: "e.g. SMU",
      namePlaceholder: "e.g. SMU - Municipal Secretariat of Urbanism",
      createNameButton: "Create name",
      editTerm: "Edit this term",
      retireTerm: "The term stops being refused as a subject.",
      reactivateTerm: "The term is refused as a subject again.",
      tagsBadgeTitle: "Tags with exactly this spelling",
      spellingField: "Spelling as It Appears in the Collection",
      kindField: "Type",
      newTerm: "+ New term",
      createCollectionTerm: "Create a collection term",
      termHint: "A spelling the collection carries and that is not a subject.",
      spellingFieldShort: "Spelling",
      spellingPlaceholder: "e.g. batel",
      createTermButton: "Create term",
      unsaved: "unsaved changes",
    },
    health: {
      verified:
        "Checked at {date}. Each check has its own timeout: a service that is down appears as a red card, not as a broken screen.",
      responding: "responding",
      offline: "offline",
      databaseTitle: "Collection",
      documents: "{count} descriptions",
      tags: "{count} tags",
      entities: "{count} entities",
      staging: "{count} records awaiting transfer",
      ollamaTitle: "Models (Ollama)",
      addressDefault: "address {host} (local default)",
      addressConfigured: "address {host} (set in the configuration)",
      installedModels: "installed models: {count}",
      requiredModels: "required models: {list}",
      noRequiredModels: "no model is required",
      missingModels: "Missing on the server: {list}. A run that needs one of them fails while loading the model.",
      storageTitle: "Thumbnail storage",
      configured: "configured",
      notConfigured: "not configured",
      endpoint: "address {endpoint}",
      noEndpoint: "no address",
      bucket: "storage bucket {bucket}",
      noBucket: "no storage bucket",
      originsTitle: "Origins",
      originsActive: "{enabled} of {total} origins active",
      originEnabled: "active",
      originPaused: "paused",
      noOrigins: "no origin configured",
      originsNote: "the queue, the agenda and each origin's configuration live on the origins screen",
      openOrigins: "Open origins",
      configTitle: "Configuration in use",
      logLine: "records {level}{detailed} in {dir}",
      logDetailed: " · detailed mode",
      databaseLine: "collection in {path}",
      ollamaLine: "models in {url}",
      storageLine: "storage in {url}",
      scrapeLine: "default origin address: {state}",
      defined: "set",
      notDefined: "not set",
      secretsLine: "keys and passwords configured: {list}",
      yes: "yes",
      no: "no",
    },
    levels: {
      status: "{levels} levels · {documents} classified descriptions",
      normNotice:
        "The norm is the default, not the law. An unknown level that arrives with the import enters — the description stays without a level and the diagnosis lists it — while the archivist cannot save a level that does not exist. Without that difference, a whole batch would fail over a new spelling.",
      editToggle: "Edit this level",
      ordinalTitle: "Position on the ladder; not editable after creation",
      activeBadge: "active",
      retiredBadge: "retired",
      documentsBadgeTitle: "Descriptions classified at this level",
      nameField: "Name",
      aliasesField: "Accepted Spellings (comma-separated)",
      aliasesPlaceholder: "e.g. subseries, sub-serie",
      descriptionField: "Description (what the archivist reads)",
      requiresParent: "requires a parent unit",
      allowsChildren: "may have children",
      unsaved: "unsaved changes",
      newRung: "+ New rung",
      addRung: "Add a rung",
      ordinalFixed: "Every rung has a fixed ordinal: check the ladder before choosing the number.",
      ordinalExplanation:
        "The ordinal is the position on the ladder: a level can only be a child of one with a lower ordinal, and once created it does not change — renumbering would change the tree already arranged with these numbers. A new ordinal and a new code create a new rung.",
      ordinalField: "Ordinal",
      codeField: "Code",
      codePlaceholder: "e.g. series",
      namePlaceholder: "e.g. Series",
      aliasesFieldShort: "Accepted Spellings",
      descriptionFieldShort: "Description",
      createLevel: "Create level",
    },
    categories: {
      tabDescriptions: "Descriptions",
      newCategory: "+ New Category",
      createTitle: "Create a Category",
      createNote: "A new category only takes effect when the classifier runs again.",
      classifierNote:
        "The classifier notices on its own when the set of categories changes and classifies the tags again on the next run.",
      namePlaceholder: "name, e.g. Health",
      descriptionPlaceholder: "curator description (never goes to the model)",
      activeSection: "Active",
      retiredSection: "Retired",
      retiredNote:
        "They left the subject axis because they are provenance and geography, not subjects. They were never deleted: they stay marked as retired, because deleting a category would erase the record that it existed.",
      seeDescriptions: "See this Category's descriptions",
      activeBadge: "active",
      retiredBadge: "retired",
      descriptionsBadgeTitle: "Descriptions with at least one tag in this category",
      descriptionsCount: "{count} descriptions",
      nameField: "Name",
      classifierLabelField: "Label the Model Reads (empty: uses the name)",
      curatorDescriptionField: "Curator Description (never goes to the model)",
      unsaved: "unsaved changes",
      emptyActiveTitle: "No description in this category",
      emptyActiveHint:
        "No tag in this category is linked to a description yet. Tags without a subject category are on the Classify tab, in Tags.",
      emptyRetiredTitle: "Retired and empty category",
      emptyRetiredHint:
        "It left the subject axis, and the classifier no longer proposes it — that is why no description carries it. It stays in the catalogue, retired: deleting a category would erase the record that it existed.",
      status: "{active} active · {retired} retired · {documents} descriptions with a category",
    },
    discover: {
      currentCategories: "Current Categories",
      groupByTheme: "Group by theme",
      intro:
        "The grouping runs on demand and takes a few seconds. The lists below are only suggestions: no term in the vocabulary changes without your approval.",
      fromTags: "From Tags",
      fromDocuments: "From Documents",
      grouping: "Grouping… (may take a few seconds)",
      propose: "Propose Categories",
      readColumns: "The grouping reads the text of these fields.",
      defaultColumn: "(default)",
      chooseColumn: "Choose at least one field.",
      emptyTitle: "No new proposal",
      emptyHint: "The grouping found no new theme, or the proposals were already dismissed.",
      seeSamples: "See the grouping's samples",
      estimates: "{count} estimates",
      topic: "topic #{id}",
      created: "Created",
      createCategory: "Create category",
      categoryName: "Category Name",
      usedOnNextRun: "The category is only used when the classification runs again.",
    },
    deletions: {
      notice:
        "Permanent deletion history. The items in this list were permanently deleted and cannot be restored. This page preserves the original data and the person responsible for the action for consultation and audit only.",
      status: "{count} item(s) in the deletion history",
      statusTerm: "{count} item(s) in the deletion history for “{term}”",
      emptyTitleTerm: "No deleted item found for “{term}”",
      emptyTitleNone: "No deleted item yet",
      emptyHintTerm: "Try another term, reference code or ID.",
      emptyHintNone:
        "The collection has no deletion records. When an item is removed, the complete data history will appear here for consultation.",
      recordId: "Record ID",
      noReference: "No reference code",
      deletedBy: "· Deleted by {name}",
      unknownUser: "unidentified user",
      children: "· Contained {count} linked item(s)",
      searchPlaceholder: "Search by code, title or ID...",
      clearSearch: "Clear search",
    },
    diagnostics: {
      noLevel: "no level",
      codeLabel: "code:",
      counting: "Counting the problems…",
      emptyTitle: "No description with this problem",
      emptyHint:
        "The diagnosis ran and found nothing of this kind. For the divergent path, this is the expected result: when a description moves, the whole branch's path is rewritten at once.",
      openDescription: "Open the description",
      openPlan: "Open the arrangement plan",
      overlap:
        "The counts overlap on purpose: the same description can appear under more than one problem — a Dossier at the root counts under “{orphan}” and under “{dossier}” — so there is no grand total.",
    },
    thumbnail: {
      unavailable: "Image unavailable",
      none: "No image",
      alt: "Description image: {title}",
      unavailableHeading: "Image Unavailable",
      storedHeading: "Stored Thumbnail",
      noSourceHeading: "No source image",
      unreadable: "The stored image could not be read",
      storedCaption: "Stored in the collection; the dossier shows the thumbnail, not the original file.",
      noSourceCaption: "This record's origin publishes no image; the description remains complete without it.",
    },
    preview: {
      published: "published",
      notPublished: "not published",
      data: "Date",
      level: "Level",
      typology: "Typology",
      arrangement: "Arrangement",
      tagsAndCategory: "Tags and Category",
      noTags: "No tags in this description.",
      anomaly: "anomaly",
      panelLabel: "Preview of {title}",
      noCategoryTitle: "This tag has no category yet",
      noCategory: "no category",
    },
    workers: { painel: "Panel", execucoes: "Runs" },
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
  isad: {
    datePlaceholder: "E.g. 1985-03-14, 1980s or a range",
    areas: {
      identity: {
        title: "3.1 Identity",
        hint: "What the description is: code, level, dates and extent.",
      },
      context: {
        title: "3.2 Context",
        hint: "Who produced it, how the collection arrived here and where the record came from.",
      },
      content: {
        title: "3.3 Content and Structure",
        hint: "What the document says and how the collection is organised.",
      },
      access: {
        title: "3.4 Access and Use",
        hint: "Who may consult it, how to reproduce it and what is needed to use the document.",
      },
      allied: {
        title: "3.5 Related Materials",
        hint: "Where the originals and copies are, and which other descriptions relate to this one.",
      },
      notes: {
        title: "3.6 Notes",
        hint: "General observations and observations about the conservation state.",
      },
      control: {
        title: "3.7 Description Control",
        hint: "Who described it, under which rules and when.",
      },
    },
    fields: {
      reference_code: {
        label: "Reference Code",
        help: "The code that identifies the unit of description in the arrangement.",
      },
      document_date: {
        label: "Document Date",
        help: "YYYY-MM-DD, or the expression as it appears in the source (1980s, 1951-1953).",
      },
      dimension_support: {
        label: "Extent and Medium",
        help: "Quantity and medium of the material. E.g. 2 leaves; 1 photograph on paper; 3.5 m of textual records.",
      },
      producers: {
        label: "Producer(s)",
        help: "Who produced the collection: the institution or the person. The list suggests entity names; choosing one copies the name without creating a link.",
      },
      admin_bio_history: {
        label: "Administrative History / Biography",
        help: "The trajectory of the producing entity or person, to contextualise the creation and use of the documents.",
      },
      admin_archival_history: {
        label: "Archival History",
        help: "Information about custody, provenance, accumulation, changes of ownership or alterations in the arrangement over time.",
      },
      provenance: {
        label: "Provenance",
        help: "Identification of the immediate source of acquisition or transfer (donor, seller, collector or previous custodian).",
      },
      scope_content: {
        label: "Scope and Content",
        help: "A summary of the central theme, temporal reach, functions and activities represented, and the main entities or individuals mentioned.",
      },
      appraisal_destruction: {
        label: "Appraisal and Destruction",
        help: "The retention period and the destruction decision, when there is one.",
      },
      accruals: {
        label: "Accruals",
        help: "Whether additions or new entries of documents are expected for this unit of description (open or closed collection).",
      },
      arrangement: {
        label: "System of Arrangement",
        help: "Information about the organisation structure, classification plan and internal ordering criteria of the unit of description.",
      },
      access_conditions: {
        label: "Conditions Governing Access",
        help: "Information about the legal status or regulations that restrict or authorise public access to the unit of description.",
      },
      reproduction_conditions: {
        label: "Conditions Governing Reproduction",
        help: "Restrictions related to copyright, reproduction (copies, photographs) or publication of the documents.",
      },
      language_name: {
        label: "Language",
        help: "The predominant language of the document.",
      },
      physical_characteristics: {
        label: "Physical Characteristics",
        help: "Information about the conservation state, physical medium and technical or preservation requirements for consulting the documents.",
      },
      finding_aids: {
        label: "Finding Aids",
        help: "Reference to guides, inventories, repertories or databases that help locate and access the unit of description.",
      },
      originals_location: {
        label: "Existence and Location of Originals",
        help: "Address or institution holding the original documentation when the unit of description consists of copies.",
      },
      copies_location: {
        label: "Existence and Location of Copies",
        help: "Information about copies in other formats or media, and their location or identification in the collection.",
      },
      related_units: {
        label: "Related Units of Description",
        help: "Cross-references to other units of description with which this collection shares provenance or a thematic relation.",
      },
      publication_notes: {
        label: "Publication Notes",
        help: "Bibliographic references of publications based on the research, use or reproduction of the unit of description.",
      },
      general_notes: {
        label: "General Notes",
        help: "Additional information that could not be included in the previous fields of the archival description.",
      },
      conservation_notes: {
        label: "Conservation Notes",
        help: "Record of damage, preservation conditions and conservation or restoration treatments applied or required.",
      },
      archivist_notes: {
        label: "Archivist's Notes",
        help: "Notes about the work of the person responsible for the description, procedures adopted and archival decisions.",
      },
      rules_conventions: {
        label: "Rules or Conventions",
        help: "Identification of the international, national or institutional standards used in preparing the record.",
      },
      description_dates: {
        label: "Dates of Description",
        help: "Chronological record of the preparation, revision and updates of the archival record.",
      },
    },
  },
  hierarchy: {
    planStatus: { SUGGESTED: "Suggested", APPROVED: "Approved", REJECTED: "Rejected" },
    planFlag: {
      ORDINAL_INFERRED: {
        label: "inferred level",
        hint: "The ordinal came from no existing record: it is a proposal, not a declaration. Decide the level by looking at the levels already declared below.",
      },
      RECORD_WITHOUT_DOCUMENTS: {
        label: "record without documents",
        hint: "A record with this code exists and no description is linked to it. Adopting it preserves the identity already in the collection.",
      },
      DUPLICATE_REFERENCE_CODE: {
        label: "duplicate code",
        hint: "More than one record uses this code, so there is no single unit to adopt: decide which record is the unit.",
      },
      NEAR_DUPLICATE_NODE: {
        label: "twin of another rung",
        hint: "A sibling differs by one letter (PHOTOGRAPH x PHOTOGRAPHS). The similarity decides nothing: decide whether this rung exists or merges into the other.",
      },
      LEVEL_NOT_ALLOWED_AS_CHILD: {
        label: "level does not fit under the parent",
        hint: "The proposed level does not come after the parent's level on the ladder, and the tree does not accept creating it like that. Merge into an existing rung or choose another level.",
      },
      MID_CODE_IDENTIFIER: {
        label: "identifier inside the code",
        hint: "There is an identifier before the last arrangement vocabulary term: the code split is a guess.",
      },
      UNPARSED_TAIL: {
        label: "unreadable code tail",
        hint: "The code's tail is not only a number (e.g. '(1)', '369B'). The code is listed as it is, never guessed.",
      },
      NO_STRUCTURAL_TOKEN: {
        label: "code without vocabulary",
        hint: "The code carries no arrangement vocabulary term: there is no rung to propose.",
      },
    },
    planAction: { CREATE: "create", ADOPT: "adopt", ALREADY: "already in the tree" },
    issue: {
      ORPHAN: {
        label: "No parent unit",
        hint: "A description without a parent unit whose level requires one, plus those with no level at all and therefore not judgeable. The fix is to materialise this branch's arrangement — or confirm it has no approved rung.",
        actionLabel: "Go to the arrangement plan",
        actionHint: "The arrangement is materialised from the approved rungs.",
      },
      DOSSIER_WITHOUT_PARENT: {
        label: "Dossier at the root",
        hint: "The narrower named case of the previous one: a Dossier — a level that requires a parent unit — stopped at the root.",
        actionLabel: "Go to the arrangement plan",
        actionHint: "A Dossier requires a parent: approve the rung above it.",
      },
      UNKNOWN_LEVEL: {
        label: "Unclassified level",
        hint: "The import tolerates an unknown level on purpose; the archivist does not. Fix the level in the description itself.",
        actionLabel: "Fix it in the description",
        actionHint: "Open the description and choose the description level on the Arrangement tab.",
      },
      PATH_DIVERGENCE: {
        label: "Divergent path",
        hint: "The recorded path does not match the parent's. It must always be zero: the path is fully rewritten when a description moves. If it appears, the path was changed outside the description's movement.",
        actionLabel: "Fix it in the description",
        actionHint: "The path is rewritten when the description moves: check the parent unit.",
      },
      LEVEL_DEPTH_MISMATCH: {
        label: "Level and code depth",
        hint: "The declared level is a minority at that code depth. The norm comes from the collection, not the code: a five-part code can carry Items, a Series and a Section at the same time.",
        actionLabel: "Fix it in the description",
        actionHint: "Review the declared level: it is a minority at that code depth.",
      },
    },
    detail: {
      code_depth: "code depth",
      expected_ordinal: "expected ordinal",
      declared_ordinal: "declared ordinal",
      path: "current path",
      expected_path: "expected path",
    },
  },
  taxonomy: {
    mergeReason: { TRIGRAM: "similar spelling", PLURAL: "singular/plural", MIXED: "spelling and plural" },
    reviewFlag: {
      MEMBER_WITH_DIGITS: {
        label: "member with digits",
        hint: "A member has a number in its name. It may be the same thing (br-116 / br 116) or another (street / street 7): the number does not decide.",
      },
      WEAK_MEMBER: {
        label: "weak member",
        hint: "Some member's similarity to the canonical one is low; the grouping may be joining different things.",
      },
      CATEGORY_WOULD_BE_LOST: {
        label: "category would be lost",
        hint: "One of the members is in a subject category the canonical one does not have. Merging drops that classification.",
      },
      MEMBER_IS_SYNONYM: {
        label: "member is an absorbed spelling",
        hint: "A member is a spelling already absorbed by an earlier merge — the grouping may reflect an old decision.",
      },
    },
    proposalStatus: {
      SUGGESTED: "suggested",
      APPROVED: "approved",
      REJECTED: "rejected",
      APPLIED: "applied",
    },
    stopwordScope: {
      TAG: {
        label: "subject (tags)",
        hint: "The term leaves the subject axis. The exclusion of the tags with that name records each one, with an undo.",
      },
      ENTITY: {
        label: "named entities",
        hint: "The term leaves the proper-name extraction. It affects no tag.",
      },
      ALL: {
        label: "both axes",
        hint: "The term leaves both axes, and the tag exclusion reaches it.",
      },
    },
    stopwordMatch: {
      TOKEN: {
        label: "the word and the names containing it",
        hint: "Blocks the word and any name containing it as a whole word — what catches the name the extractor returns with it (IPTU do Exemplo).",
      },
      EXACT: {
        label: "only the exact spelling",
        hint: "Blocks only the whole word. A name that merely starts with or contains the word passes: alameda alone is noise, Alameda Cabral is a street.",
      },
    },
    stopwordSource: {
      HUMAN: {
        label: "typed here",
        hint: "Someone typed this spelling in Blocked spellings: it is a deliberate act.",
      },
      CONFLICT: {
        label: "came from a tag × entity conflict",
        hint: "The term was banned when a conflict between the tag and the entity with the same spelling was resolved.",
      },
      EXCLUSION: {
        label: "came from “not a subject”",
        hint: "The term was banned together with the “not a subject” decision. Undoing that decision lifts this ban.",
      },
    },
    catalogState: {
      ALL: {
        label: "All",
        hint: "Complete list of terms, ordered by frequency of use.",
      },
      PENDING: {
        label: "No decision",
        hint: "Terms awaiting manual and automatic evaluation.",
      },
      NOT_SUBJECT: {
        label: "Not a subject",
        hint: "Term manually marked as not being a subject. The term is blocked from new tags, but current occurrences stay in the collection and remain findable in search.",
      },
      LOW_CONFIDENCE: {
        label: "Low confidence",
        hint: "Inconclusive automatic classification. The tag awaits human validation, with the score suggested by the system shown on the row.",
      },
    },
  },
  quality: {
    ruleKind: {
      REWRITE: {
        label: "rewrites the text",
        hint: "The rule replaces every occurrence with the replacement text. It is the only kind of rule that touches the collection.",
      },
      VALIDATE: {
        label: "only flags",
        hint: "The rule does not touch the text: when the expression matches, the description gets an anomaly with the declared reason.",
      },
      LLM_CHECK: {
        label: "asks the model",
        hint: "A language model gives an opinion on the title. Without an active rule of this kind, the model is not loaded.",
      },
    },
    targetColumn: {
      original_title: "original title",
      scope_content: "scope and content",
      admin_bio_history: "administrative history",
      provenance: "provenance",
      archivist_notes: "archivist's notes",
    },
    templateStatus: { SUGGESTED: "suggested", APPROVED: "approved", REJECTED: "rejected" },
    templateAction: { IGNORE: "remove from the text", REPLACE: "replace" },
    templateScope: {
      EMBEDDING: {
        label: "meaning search",
        hint: "The excerpt leaves the text used in the meaning search. It is where the gain is largest: more than half the collection repeated the same block.",
      },
      NER: {
        label: "name extraction",
        hint: "The excerpt leaves the text the name extraction and the classifier read.",
      },
      TITLE: {
        label: "suggested title",
        hint: "The excerpt leaves the suggested title. The prefix 'Registros Fotográficos -' helps here and hurts the meaning search — that is why the scopes are separate.",
      },
    },
    anomalyReason: {
      MISSING_DATE: { label: "no date", hint: "" },
      FUTURE_DATE: { label: "future date", hint: "" },
      EMPTY_TITLE: { label: "empty title", hint: "" },
      ALL_CAPS_TITLE: { label: "all-caps title", hint: "" },
      REPEATED_TITLE: { label: "repeated title", hint: "" },
      TITLE_ONLY_TEMPLATE: { label: "title only from a source excerpt", hint: "" },
      SCOPE_ONLY_BOILERPLATE: { label: "scope only repeated text", hint: "" },
      NO_TAGS: { label: "no subjects", hint: "" },
      NO_TYPOLOGY: { label: "no typology", hint: "" },
      NO_ENTITIES: { label: "no named entities", hint: "" },
      RULE_MATCH: {
        label: "archivist rule",
        hint: "An active rule that only flags or asks the model matched. The rule's name comes after the colon and is what the filter uses.",
      },
      LLM_SUSPECT: {
        label: "model suspicion",
        hint: "The model found the title suspicious. What it wrote stays on the record, not in the filter: a facet over that text would have options that never repeat.",
      },
    },
    signal: {
      PLACEHOLDER: {
        label: "placeholder text",
        hint: "The import writes this text when the data did not arrive: it is about no subject at all.",
      },
      YEAR: {
        label: "isolated year",
        hint: "A loose year is a date, not a subject — and the model used to classify it as a subject.",
      },
      MEASURE: { label: "number with unit", hint: "A number with a unit is a measure, not a concept." },
      STREET: {
        label: "street address",
        hint: "A street address is a place: it is not a subject, and the entity axis carries the place.",
      },
      PERSON: {
        label: "person name",
        hint: "A person's name is a producer or a biographee, not a subject: the entity axis carries it.",
      },
      RECORDED: {
        label: "recorded decision",
        hint: "It does not follow a recognisable format: it was someone's decision, and that decision is the reason.",
      },
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
