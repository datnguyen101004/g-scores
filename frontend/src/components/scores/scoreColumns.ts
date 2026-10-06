import type { Student } from "@/types/student";
import type { Locale } from "@/i18n/languages";

export type ScoreSubject = Exclude<keyof Student, "sbd" | "maNgoaiNgu">;

export const scoreColumns: { key: ScoreSubject; labelKey: `subjects.${ScoreSubject}` }[] = [
  { key: "toan", labelKey: "subjects.toan" },
  { key: "nguVan", labelKey: "subjects.nguVan" },
  { key: "ngoaiNgu", labelKey: "subjects.ngoaiNgu" },
  { key: "vatLi", labelKey: "subjects.vatLi" },
  { key: "hoaHoc", labelKey: "subjects.hoaHoc" },
  { key: "sinhHoc", labelKey: "subjects.sinhHoc" },
  { key: "lichSu", labelKey: "subjects.lichSu" },
  { key: "diaLi", labelKey: "subjects.diaLi" },
  { key: "gdcd", labelKey: "subjects.gdcd" },
];

const scoreFormatters = {
  vi: new Intl.NumberFormat("vi-VN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }),
  en: new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }),
};

export const formatScore = (score: number | null, language: Locale): string =>
  score === null ? "—" : scoreFormatters[language].format(score);
