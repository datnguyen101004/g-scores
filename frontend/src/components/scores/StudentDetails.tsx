import { useTranslation } from "react-i18next";
import type { Student } from "@/types/student";
import { formatScore, scoreColumns } from "./scoreColumns";

export default function StudentDetails({ student }: { student: Student }) {
  const { t, i18n } = useTranslation("scores");
  const language = (i18n.resolvedLanguage ?? i18n.language).startsWith("vi") ? "vi" : "en";
  return (
    <div className="mt-5 rounded-xl border border-brand-100 bg-brand-50/50 p-4 sm:p-5 dark:border-brand-500/20 dark:bg-brand-500/5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold text-gray-800 dark:text-white/90">
          {t("student.registrationNumber")} <span className="ml-2 font-mono text-brand-600 dark:text-brand-400">{student.sbd}</span>
        </h3>
        <p className="text-sm text-gray-500 dark:text-gray-400">{t("student.foreignLanguageCode")}: {student.maNgoaiNgu ?? "—"}</p>
      </div>
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
        {scoreColumns.map(({ key, labelKey }) => (
          <div key={key} className="rounded-lg border border-gray-100 bg-white p-3 dark:border-gray-800 dark:bg-gray-900">
            <dt className="text-xs text-gray-500 dark:text-gray-400">{t(labelKey)}</dt>
            <dd className="mt-1 text-xl font-semibold tabular-nums text-gray-800 dark:text-white/90">{formatScore(student[key], language)}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-4 text-sm text-gray-500 dark:text-gray-400">{t("student.missingScoreHint")}</p>
    </div>
  );
}
