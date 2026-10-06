import { lazy, Suspense, useState } from "react";
import type { ApexOptions } from "apexcharts";
import { useTranslation } from "react-i18next";
import Button from "@/components/ui/button/Button";
import { scoreColumns } from "@/components/scores/scoreColumns";
import { useTheme } from "@/context/ThemeContext";
import { useApiResource } from "@/hooks/useApiResource";

const Chart = lazy(() => import("react-apexcharts"));
const scoreBands = ["GTE_8", "FROM_6_TO_8", "FROM_4_TO_6", "LT_4"] as const;
type ScoreBand = (typeof scoreBands)[number];
type Subject = (typeof scoreColumns)[number]["key"];

interface ReportCount {
  subject: Subject;
  scoreBand: ScoreBand;
  count: number;
}

export default function ScoreDistributionChart() {
  const { t, i18n } = useTranslation("scores");
  const { theme } = useTheme();
  const [subject, setSubject] = useState<Subject>("toan");
  const baseUrl = `/api/reports/students?subject=${subject}&scoreBand=`;
  const high = useApiResource<ReportCount>(`${baseUrl}GTE_8`);
  const good = useApiResource<ReportCount>(`${baseUrl}FROM_6_TO_8`);
  const average = useApiResource<ReportCount>(`${baseUrl}FROM_4_TO_6`);
  const low = useApiResource<ReportCount>(`${baseUrl}LT_4`);
  const resources = [high, good, average, low];
  const loading = resources.some((resource) => resource.loading);
  const error = resources.find((resource) => resource.error)?.error;
  const complete = resources.every((resource) => resource.data !== null);
  const counts = complete ? resources.map((resource) => resource.data!.count) : [];
  const locale = (i18n.resolvedLanguage ?? i18n.language).startsWith("vi") ? "vi-VN" : "en-US";
  const numberFormatter = new Intl.NumberFormat(locale, { maximumFractionDigits: 0 });
  const formatCount = (value: number) => numberFormatter.format(value);
  const labels = scoreBands.map((band) => t(`report.distribution.bands.${band}`));
  const total = counts.reduce((sum, count) => sum + count, 0);
  const title = t("report.distribution.chartLabel", { subject: t(`subjects.${subject}`) });
  const options: ApexOptions = {
    chart: {
      type: "bar",
      fontFamily: "Rubik, sans-serif",
      background: "transparent",
      foreColor: theme === "dark" ? "#98a2b3" : "#667085",
      toolbar: { show: false },
      animations: { enabled: false },
    },
    theme: { mode: theme },
    colors: ["#465fff", "#12b76a", "#f79009", "#f04438"],
    plotOptions: {
      bar: { horizontal: false, distributed: true, columnWidth: "45%", borderRadius: 5, borderRadiusApplication: "end" },
    },
    dataLabels: { enabled: false },
    legend: { show: false },
    xaxis: {
      categories: ["≥ 8", "6–<8", "4–<6", "< 4"],
      axisBorder: { show: false },
      axisTicks: { show: false },
      labels: { rotate: 0, trim: false, hideOverlappingLabels: false },
    },
    yaxis: { min: 0, decimalsInFloat: 0, forceNiceScale: true, labels: { formatter: formatCount } },
    grid: { borderColor: theme === "dark" ? "#344054" : "#eaecf0" },
    fill: { opacity: 1 },
    tooltip: { theme, y: { formatter: formatCount } },
  };


  return (
    <section aria-labelledby="score-distribution-title" aria-busy={loading} className="min-w-0 rounded-2xl border border-gray-200 bg-white p-5 sm:p-6 dark:border-gray-800 dark:bg-gray-900">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 id="score-distribution-title" className="text-lg font-semibold text-gray-800 dark:text-white/90">{t("report.distribution.title")}</h2>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{t("report.distribution.description")}</p>
        </div>
        <div className="w-full shrink-0 sm:w-48">
          <label htmlFor="report-subject" className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">{t("report.distribution.subject")}</label>
          <select id="report-subject" value={subject} onChange={(event) => setSubject(event.target.value as Subject)} className="h-11 w-full rounded-lg border border-gray-300 bg-white px-3 text-sm text-gray-800 focus:border-brand-300 focus:outline-2 focus:outline-brand-500 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90">
            {scoreColumns.map((column) => <option key={column.key} value={column.key}>{t(column.labelKey)}</option>)}
          </select>
        </div>
      </div>
      <div className="mt-5" aria-live="polite">
        {error ? (
          <div role="alert" className="rounded-xl border border-error-500/30 bg-error-500/5 p-4">
            <h3 className="text-sm font-semibold text-gray-800 dark:text-white/90">{t(error.statusCode === null ? "errors.network.title" : "report.distribution.errorTitle")}</h3>
            <p className="mt-1 text-sm text-gray-700 dark:text-gray-300">{t(error.statusCode === null ? "errors.network.message" : "report.errorMessage")}</p>
            <Button size="sm" variant="outline" onClick={() => resources.forEach((resource) => resource.refetch())} className="mt-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500">{t("errors.retry")}</Button>
          </div>
        ) : loading ? (
          <p role="status" className="text-sm text-gray-500 dark:text-gray-400">{t("report.distribution.loading")}</p>
        ) : complete && (
          <>
            <p className="text-sm text-gray-500 dark:text-gray-400">{t("report.distribution.total", { count: formatCount(total) })}</p>
            {total === 0 ? (
              <p role="status" className="mt-4 text-sm text-gray-500 dark:text-gray-400">{t("report.distribution.empty")}</p>
            ) : (
              <div role="img" aria-label={title} className="min-w-0">
                <Suspense fallback={<p role="status" className="py-6 text-sm text-gray-500 dark:text-gray-400">{t("report.distribution.loading")}</p>}>
                  <Chart options={options} series={[{ name: t("report.distribution.students"), data: counts }]} type="bar" height={300} width="100%" />
                </Suspense>
              </div>
            )}
            <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
              {scoreBands.map((band, index) => (
                <div key={band} className="rounded-xl border border-gray-200 bg-gray-50 p-3 dark:border-gray-800 dark:bg-gray-800/50">
                  <dt className="text-sm text-gray-500 dark:text-gray-400">{labels[index]}</dt>
                  <dd data-score-band={band} className="mt-1 text-lg font-semibold text-gray-800 tabular-nums dark:text-white/90">{formatCount(counts[index])}</dd>
                </div>
              ))}
            </dl>
          </>
        )}
      </div>
    </section>
  );
}
