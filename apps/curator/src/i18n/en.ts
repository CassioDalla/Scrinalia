/**
 * The English catalogue: typed as the Portuguese one, so a missing or extra message fails `tsc`
 * (ADR 0020 §1).
 */

import type { pt } from "./pt";

export const en: typeof pt = {
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
