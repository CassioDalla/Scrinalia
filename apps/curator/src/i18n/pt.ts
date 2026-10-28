/**
 * The Portuguese catalogue: the source of the interface's copy (ADR 0020).
 *
 * Portuguese is canonical here, unlike the documentation: the person doing the work reads it first,
 * so a missing English string must fail the build instead of falling back to this one. `en.ts` is
 * typed as this object, which is the gate.
 *
 * A message is a string with `{name}` placeholders; the `Trans` component renders the markup the
 * placeholder carries. The screens hold keys, never copy.
 */

export const pt = {
  format: {
    /** `formatDate`'s answer for a record that has no date. */
    noDate: "sem data",
    /** The two forms `descricoes` needs; the plural rule is `Intl.PluralRules`. */
    descriptions: { one: "descrição", other: "descrições" },
  },
  notFound: {
    title: "Tela não encontrada",
    hint: "O endereço não corresponde a nenhuma tela do sistema.",
    backHome: "Voltar ao início",
  },
  attribution: {
    license: "Licença",
    source: "Código-fonte",
    version: "Versão da instalação",
  },
  auth: {
    login: {
      email: "E-mail",
      password: "Senha",
      signIn: "Entrar",
      signingIn: "Entrando…",
      failure: "Não foi possível entrar.",
      forgot: "Esqueci minha senha",
      noMessage:
        "Nenhuma mensagem é enviada por esta tela. Um administrador redefine a sua senha em {settings}, na conta certa.",
      settingsPath: "Configurações → Usuários",
      lastAdmin:
        "Se a conta for a última de administrador ativa e ninguém conseguir entrar, o acesso é recolocado pelo terminal do servidor, por quem opera a máquina (guia de operação).",
    },
    setup: {
      title: "Primeiro acesso da instalação",
      explanation:
        "Esta instalação ainda não tem contas, e a conta de administração só pode ser criada uma vez. Ela administra o sistema e cria as demais em Configurações › Usuários.",
      email: "E-mail",
      name: "Nome",
      password: "Senha",
      confirmation: "Confirmação da Senha",
      mismatch: "As duas senhas não coincidem.",
      failure: "Não foi possível criar a conta.",
      create: "Criar conta",
      creating: "Criando…",
      noRecovery:
        "Não há recuperação de senha por e-mail: guarde esta senha. Se ela for perdida, só quem administra a instalação pode definir outra.",
    },
    password: {
      title: "Trocar senha",
      forced:
        "Esta conta ainda usa a senha temporária do primeiro acesso. Escolha uma senha sua para continuar.",
      voluntary: "As outras sessões desta conta serão encerradas.",
      current: "Senha Atual",
      next: "Nova Senha",
      confirmation: "Confirmação da Nova Senha",
      mismatch: "As duas senhas não coincidem.",
      failure: "Não foi possível trocar a senha.",
      changing: "Trocando…",
      change: "Trocar senha",
      cancel: "Cancelar",
    },
  },
};

/** The shape every locale's catalogue has; `en.ts` is typed as this. */
export type Messages = typeof pt;
