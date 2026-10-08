import { useTranslation } from "react-i18next";
import PageMeta from "@/components/common/PageMeta";
import Button from "@/components/ui/button/Button";
import { formatScore } from "@/components/scores/scoreColumns";
import ScoreDistributionChart from "@/components/scores/ScoreDistributionChart";
import { useApiResource } from "@/hooks/useApiResource";
import type { TopStudents } from "@/types/student";

export default function ScoresReport() {
  const { t, i18n } = useTranslation("scores");
  const ranking = useApiResource<TopStudents>("/api/students/top-10");
  const language = (i18n.resolvedLanguage ?? i18n.language).startsWith("vi") ? "vi" : "en";
  const cellClass = "px-4 py-3 text-right tabular-nums whitespace-nowrap";

  return (
    <div className="min-w-0 space-y-6">
      <PageMeta title={t("report.metaTitle")} description={t("report.overviewDescription")} />
      <div>
        <h1 className="text-2xl font-semibold text-gray-800 dark:text-white/90">{t("report.overview")}</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{t("report.overviewDescription")}</p>
      </div>
      <ScoreDistributionChart />
      <section aria-label={t("report.title")} aria-busy={ranking.loading} className="min-w-0 rounded-2xl border border-gray-200 bg-white p-5 sm:p-6 dark:border-gray-800 dark:bg-gray-900">
        <h2 className="mb-1 text-lg font-semibold text-gray-800 dark:text-white/90">{t("report.title")}</h2>
        <p className="mb-4 text-sm text-gray-500 dark:text-gray-400">{t("report.description")}</p>
        {ranking.loading && <p role="status" className="text-sm text-gray-500 dark:text-gray-400">{t("report.loading")}</p>}
        {ranking.error && (
          <div role="alert" className="rounded-xl border border-error-500/30 bg-error-500/5 p-4">
            <h2 className="text-sm font-semibold text-gray-800 dark:text-white/90">{t(ranking.error.kind === "timeout" ? "errors.timeout.title" : ranking.error.kind === "network" ? "errors.network.title" : "report.errorTitle")}</h2>
            <p className="mt-1 text-sm text-gray-700 dark:text-gray-300">{t(ranking.error.kind === "timeout" ? "errors.timeout.message" : ranking.error.kind === "network" ? "errors.network.message" : "report.errorMessage")}</p>
            <Button size="sm" variant="outline" onClick={ranking.refetch} className="mt-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500">{t("errors.retry")}</Button>
          </div>
        )}
        {ranking.data && (ranking.data.students.length === 0 ? (
          <p role="status" className="text-sm text-gray-500 dark:text-gray-400">{t("report.empty")}</p>
        ) : (
          <>
            <p className="mb-4 text-sm text-gray-500 dark:text-gray-400">{t("report.count", { count: ranking.data.students.length })}</p>
            <div role="region" aria-label={t("report.title")} tabIndex={0} className="overflow-x-auto rounded-lg focus-visible:outline-2 focus-visible:outline-brand-500">
              <table className="w-full text-sm text-gray-700 dark:text-gray-300">
                <caption className="sr-only">{t("report.title")}</caption>
                <thead className="border-b border-gray-200 bg-gray-50 text-gray-600 dark:border-gray-800 dark:bg-gray-800 dark:text-gray-400">
                  <tr>
                    <th scope="col" className="px-4 py-3 text-left whitespace-nowrap">{t("report.rank")}</th>
                    <th scope="col" className="px-4 py-3 text-left whitespace-nowrap">{t("student.registrationNumber")}</th>
                    <th scope="col" className={cellClass}>{t("subjects.toan")}</th>
                    <th scope="col" className={cellClass}>{t("subjects.vatLi")}</th>
                    <th scope="col" className={cellClass}>{t("subjects.hoaHoc")}</th>
                    <th scope="col" className={cellClass}>{t("report.total")}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                  {ranking.data.students.map((student) => (
                    <tr key={student.sbd}>
                      <td className="px-4 py-3 tabular-nums">{student.rank}</td>
                      <th scope="row" className="px-4 py-3 text-left font-medium tabular-nums">{student.sbd}</th>
                      <td className={cellClass}>{formatScore(student.scores.toan, language)}</td>
                      <td className={cellClass}>{formatScore(student.scores.vatLi, language)}</td>
                      <td className={cellClass}>{formatScore(student.scores.hoaHoc, language)}</td>
                      <td className={`${cellClass} font-semibold text-brand-600 dark:text-brand-400`}>{formatScore(student.totalScore, language)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ))}
      </section>
    </div>
  );
}
