import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import enCommon from "../locales/en/common.json";
import viCommon from "../locales/vi/common.json";
import enScores from "../locales/en/scores.json";
import viScores from "../locales/vi/scores.json";
import { defaultLocale, locales } from "./languages";

export const resources = {
  en: {
    common: enCommon,
    scores: enScores,
  },
  vi: {
    common: viCommon,
    scores: viScores,
  },
} as const;

export const defaultNS = "common";
export const fallbackLng = defaultLocale;

const savedLng =
  typeof window !== "undefined"
    ? localStorage.getItem("i18nextLng") || localStorage.getItem("language")
    : null;
const initialLng = locales.find((locale) => locale === savedLng) ?? defaultLocale;

i18n.use(initReactI18next).init({
  resources,
  lng: initialLng,
  fallbackLng,
  defaultNS,
  ns: ["common", "scores"],
  interpolation: {
    escapeValue: false, // React already escapes values
    prefix: "{",
    suffix: "}",
  },
});

export default i18n;
