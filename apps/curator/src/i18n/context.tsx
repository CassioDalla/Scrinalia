import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { activeLocale, messagesFor, setActiveLocale, type Locale } from "@/i18n/locale";
import type { Messages } from "@/i18n/pt";

type LocaleContextValue = {
  locale: Locale;
  /** `persist: false` when the account is the source of the choice, not this browser. */
  setLocale: (locale: Locale, options?: { persist?: boolean }) => void;
};

const LocaleContext = createContext<LocaleContextValue | null>(null);

/**
 * The active locale, for the tree.
 *
 * `setLocale` updates the module variable **before** the state, so the formatters in the render that
 * follows already use the new locale. The only side effect is the document's `lang`, which is what
 * makes a screen reader announce the right language.
 */
export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(() => activeLocale());

  const setLocale = useCallback((next: Locale, options?: { persist?: boolean }) => {
    setActiveLocale(next, options?.persist ?? true);
    setLocaleState(next);
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale;
    document.title = messagesFor(locale).product.documentTitle;
  }, [locale]);

  const value = useMemo(() => ({ locale, setLocale }), [locale, setLocale]);

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale(): LocaleContextValue {
  const value = useContext(LocaleContext);
  if (!value) throw new Error("useLocale must be used inside LocaleProvider");
  return value;
}

/** The catalogue of the active locale. The screens read `copy.auth.login.title`, never a literal. */
export function useCopy(): Messages {
  const { locale } = useLocale();
  return messagesFor(locale);
}
