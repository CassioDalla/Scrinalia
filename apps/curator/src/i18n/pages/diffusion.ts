/**
 * The diffusion channels page (issue #213, ADR 0023).
 *
 * The screen is the operator's, under Configurações → Operação, and it says one thing the rest of
 * the interface does not: **the channel does not publish**. `is_published` is the record's
 * permission to leave and the channel is where it goes, so configuring a channel changes no
 * description. The copy keeps that distinction in the subtitle (`screens.diffusion`) and in the
 * empty state, and it never calls the channel a *source*: the ingestion origin is the source of
 * data, and two opposite `source` concepts in one system is a defect waiting to be written.
 *
 * Merged into `pages` by `i18n/pt.ts` and `i18n/en.ts`; `en` is typed as `pt`, so a missing key
 * fails `tsc`.
 */

export const pt = {
  diffusion: {
    statusNone: "Nenhum canal de difusão configurado",
    statusOne: "{count} canal configurado · {active} ativo",
    statusMany: "{count} canais configurados · {active} ativos",
    addChannel: "Adicionar canal de difusão",
    emptyTitle: "Nenhum canal de difusão",
    emptyHint:
      "Esta instalação ainda não tem para onde difundir. Adicione um canal disponível para dizer por onde o acervo publicado pode sair.",
    allConfigured: "Todos os canais disponíveis já estão configurados.",
    capabilityLive: "ao vivo",
    capabilityExport: "exportação",
    activeBadge: "ativo",
    pausedBadge: "pausado",
    noOwnConfig: "Sem configuração própria: o canal usa os valores padrão.",
    noConfigFields: "Este canal não tem campos de configuração.",
    editConfig: "Editar configuração",
    scheduleTab: "Agenda",
    pause: "Desativar",
    reactivate: "Ativar",
    operatorOnly: "Configuração e agenda ficam com o operador.",
    saving: "Salvando…",
    saveConfig: "Salvar configuração",
    configSaved: "Configuração salva.",
    required: "obrigatório",
    yes: "sim",
    no: "não",
    viewSite: "Ver site",
    publicSiteNote:
      "O site público é um aplicativo separado: habilitar o canal não instala o site. O endereço configurado é o que o link abre; enquanto o aplicativo não estiver publicado ali, ele não responde.",
    lastRun: "Última execução",
    none: "nenhuma",
    schedule: "Agenda",
    nextRun: "{tz} · próxima {when}",
    noSchedule: "sem agenda",
    cronHint: "Cinco campos (minuto, hora, dia do mês, mês, dia da semana), avaliados no fuso indicado.",
    scheduleField: "Agendamento",
    timezoneField: "Fuso Horário",
    saveSchedule: "Salvar agenda",
    removeSchedule: "Remover agenda",
    addTitle: "Adicionar canal de difusão",
    addHint: "Escolha um canal que ainda não está configurado.",
    addNote: "O canal já vem pronto com o sistema; adicioná-lo aqui só o ativa nesta instalação.",
    adding: "Adicionando…",
    add: "Adicionar",
    back: "Voltar",
  },
};

export const en: typeof pt = {
  diffusion: {
    statusNone: "No diffusion channel configured",
    statusOne: "{count} channel configured · {active} active",
    statusMany: "{count} channels configured · {active} active",
    addChannel: "Add diffusion channel",
    emptyTitle: "No diffusion channel",
    emptyHint:
      "This installation has nowhere to diffuse yet. Add an available channel to say where the published collection can go.",
    allConfigured: "Every available channel is already configured.",
    capabilityLive: "live",
    capabilityExport: "export",
    activeBadge: "active",
    pausedBadge: "paused",
    noOwnConfig: "No configuration of its own: the channel uses the default values.",
    noConfigFields: "This channel has no configuration fields.",
    editConfig: "Edit configuration",
    scheduleTab: "Schedule",
    pause: "Disable",
    reactivate: "Enable",
    operatorOnly: "Configuration and schedule are the operator's.",
    saving: "Saving…",
    saveConfig: "Save configuration",
    configSaved: "Configuration saved.",
    required: "required",
    yes: "yes",
    no: "no",
    viewSite: "View site",
    publicSiteNote:
      "The public site is a separate application: enabling the channel does not install it. The configured address is what the link opens; while the application is not published there, it does not answer.",
    lastRun: "Last run",
    none: "none",
    schedule: "Schedule",
    nextRun: "{tz} · next {when}",
    noSchedule: "no schedule",
    cronHint: "Five fields (minute, hour, day of month, month, day of week), evaluated in the given zone.",
    scheduleField: "Schedule",
    timezoneField: "Timezone",
    saveSchedule: "Save schedule",
    removeSchedule: "Remove schedule",
    addTitle: "Add diffusion channel",
    addHint: "Choose a channel that is not configured yet.",
    addNote: "The channel ships with the system; adding it here only enables it in this installation.",
    adding: "Adding…",
    add: "Add",
    back: "Back",
  },
};
