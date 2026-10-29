/**
 * The diffusion channels page (issue #213, ADR 0023).
 *
 * The screen is the operator's, under Configurações → Operação, and it says one thing the rest of
 * the interface does not: **the channel does not publish**. `is_published` is the record's
 * permission to leave and the channel is where it goes, so configuring a channel changes no
 * description. The distinction is carried by the subtitle (`screens.diffusion`) and by the hint at
 * the one place it can be forgotten — the save button — and nowhere else twice.
 *
 * The voice is the origins page's, the screen this one mirrors: an introduction that says what the
 * page decides, a section title with a hint, and one sentence of help at each write. The copy never
 * calls the channel a *source*: the ingestion origin is the source of data, and two opposite
 * `source` concepts in one system is a defect waiting to be written.
 *
 * Merged into `pages` by `i18n/pt.ts` and `i18n/en.ts`; `en` is typed as `pt`, so a missing key
 * fails `tsc`.
 */

export const pt = {
  diffusion: {
    statusNone: "Nenhum canal de difusão configurado",
    statusOne: "{count} canal configurado · {active} ativo",
    statusMany: "{count} canais configurados · {active} ativos",
    intro:
      "A difusão é por onde o acervo publicado sai. Cada canal é um destino para esse acervo, com a sua configuração e — quando o canal exporta — a sua agenda. Esta página diz quais canais existem nesta instalação; nenhum vem ativo por padrão.",
    channelsTitle: "Canais",
    channelsHint:
      "Os destinos desta instalação. Desativar um canal mantém a configuração e a agenda: ele só deixa de ser oferecido a quem lê.",
    addChannel: "Adicionar canal de difusão",
    emptyTitle: "Nenhum canal de difusão",
    emptyHint:
      "Esta instalação ainda não tem para onde difundir. Adicione um canal disponível — ele já vem pronto com o sistema — para dizer por onde o acervo publicado pode sair.",
    allConfigured: "Todos os canais disponíveis já estão configurados.",
    capabilityLive: "ao vivo",
    capabilityExport: "exportação",
    capabilityLiveHint: "Lido a cada acesso: não tem execução nem agenda.",
    capabilityExportHint: "Produzido por uma execução, com agenda própria.",
    activeBadge: "ativo",
    pausedBadge: "pausado",
    noOwnConfig: "Sem configuração própria: o canal usa os valores padrão.",
    noConfigFields: "Este canal não tem campos de configuração.",
    editConfig: "Editar configuração",
    scheduleTab: "Agenda",
    pause: "Desativar",
    reactivate: "Ativar",
    enqueueRun: "Enfileirar execução",
    enqueuing: "Enfileirando…",
    alreadyRunning: "Já há uma execução",
    pausedChannel: "Canal desativado",
    queuedLine: "Execução #{id} na fila; ela ainda não começou.",
    operatorOnly:
      "Só o operador adiciona, configura e desativa canais; aqui você pode consultar os destinos e abrir o site público.",
    saving: "Salvando…",
    saveConfig: "Salvar configuração",
    configHint:
      "A configuração é o que este canal precisa saber para funcionar. Salvar aqui só grava a configuração: nada é publicado.",
    configSaved: "Configuração salva.",
    required: "obrigatório",
    yes: "sim",
    no: "não",
    viewSite: "Ver site",
    publicSiteNote:
      "O site público é um aplicativo separado: ativar o canal não instala o site. O endereço configurado é o que o botão Ver site abre; enquanto o aplicativo não estiver publicado ali, a página não responde — e isso não muda o que está publicado no acervo.",
    lastRun: "Última execução",
    none: "nenhuma",
    schedule: "Agenda",
    nextRun: "{tz} · próxima {when}",
    noSchedule: "sem agenda",
    scheduleHint:
      "Cinco campos (minuto, hora, dia do mês, mês, dia da semana), avaliados no fuso indicado. A agenda vale enquanto o canal estiver ativo; desativar o canal a suspende sem removê-la.",
    scheduleField: "Agendamento",
    timezoneField: "Fuso Horário",
    saveSchedule: "Salvar agenda",
    removeSchedule: "Remover agenda",
    addTitle: "Adicionar canal de difusão",
    addHint:
      "Escolha um canal que ainda não está configurado. A configuração dele é pedida em seguida, antes de o canal ser ativado.",
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
    intro:
      "Diffusion is how the published collection leaves. Each channel is a destination for it, with its own configuration and — when the channel exports — its own schedule. This page says which channels exist in this installation; none is active by default.",
    channelsTitle: "Channels",
    channelsHint:
      "This installation's destinations. Disabling a channel keeps its configuration and its schedule: it simply stops being offered to readers.",
    addChannel: "Add diffusion channel",
    emptyTitle: "No diffusion channel",
    emptyHint:
      "This installation has nowhere to diffuse yet. Add an available channel — it ships with the system — to say where the published collection can go.",
    allConfigured: "Every available channel is already configured.",
    capabilityLive: "live",
    capabilityExport: "export",
    capabilityLiveHint: "Read on every access: it has no run and no schedule.",
    capabilityExportHint: "Produced by a run, with a schedule of its own.",
    activeBadge: "active",
    pausedBadge: "paused",
    noOwnConfig: "No configuration of its own: the channel uses the default values.",
    noConfigFields: "This channel has no configuration fields.",
    editConfig: "Edit configuration",
    scheduleTab: "Schedule",
    pause: "Disable",
    reactivate: "Enable",
    enqueueRun: "Enqueue run",
    enqueuing: "Enqueueing…",
    alreadyRunning: "A run is already in flight",
    pausedChannel: "Channel disabled",
    queuedLine: "Run #{id} is queued; it has not started yet.",
    operatorOnly:
      "Only the operator adds, configures and disables channels; here you can consult the destinations and open the public site.",
    saving: "Saving…",
    saveConfig: "Save configuration",
    configHint:
      "The configuration is what this channel needs to work. Saving here only stores the configuration: nothing is published.",
    configSaved: "Configuration saved.",
    required: "required",
    yes: "yes",
    no: "no",
    viewSite: "View site",
    publicSiteNote:
      "The public site is a separate application: enabling the channel does not install it. The configured address is what the View site button opens; while the application is not published there, the page does not answer — and that does not change what is published in the collection.",
    lastRun: "Last run",
    none: "none",
    schedule: "Schedule",
    nextRun: "{tz} · next {when}",
    noSchedule: "no schedule",
    scheduleHint:
      "Five fields (minute, hour, day of month, month, day of week), evaluated in the given zone. The schedule holds while the channel is active; disabling the channel suspends it without removing it.",
    scheduleField: "Schedule",
    timezoneField: "Timezone",
    saveSchedule: "Save schedule",
    removeSchedule: "Remove schedule",
    addTitle: "Add diffusion channel",
    addHint:
      "Choose a channel that is not configured yet. Its configuration is asked next, before the channel is enabled.",
    addNote: "The channel ships with the system; adding it here only enables it in this installation.",
    adding: "Adding…",
    add: "Add",
    back: "Back",
  },
};
