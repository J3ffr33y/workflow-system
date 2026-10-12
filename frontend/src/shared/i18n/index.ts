/**
 * Interface text goes through i18n keys so the team can switch to Chinese.
 * English is the source language; zh-CN can be filled in progressively
 * (missing keys fall back to English).
 */
import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./en.json";
import zh from "./zh-CN.json";

i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, "zh-CN": { translation: zh } },
  lng: localStorage.getItem("locale") ?? "en",
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});

export default i18n;
