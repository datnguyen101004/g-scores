import { lazy, Suspense, useState } from "react";
import type { ApexOptions } from "apexcharts";
import { useTranslation } from "react-i18next";
import PageMeta from "@/components/common/PageMeta";
import { formatScore, scoreColumns, type ScoreSubject } from "@/components/scores/scoreColumns";
import Button from "@/components/ui/button/Button";
import { useTheme } from "@/context/ThemeContext";
import { useApiResource } from "@/hooks/useApiResource";
import type { ScoreDistribution } from "@/types/reports";

const Chart = lazy(() => import("react-apexcharts"));

export default function ScoreOverview() {
  const { t, i18n } = useTranslation("scores");
  const { theme } = useTheme();
  const [subject, setSubject] = useState<ScoreSubject>("toan");
  const resource = useApiResource<ScoreDistribution>(
    `/api/reports/distribution?subject=${subject}`,
  );
  const locale = (i18n.resolvedLanguage ?? i18n.language).startsWith("vi")
    ? "vi-VN"
    : "en-US";
  const language = locale === "vi-VN" ? "vi" : "en";
  const countFormatter = new Intl.NumberFormat(locale, { maximumFractionDigits: 0 });
  const boundaryFormatter = new Intl.NumberFormat(locale, { maximumFractionDigits: 1 });
  const data = resource.data;
  const intervalLabels = data?.bins.map((bin) => {
    const lower = boundaryFormatter.format(bin.lowerBound);
    const upper = boundaryFormatter.format(bin.upperBound);
    return `${lower}-${upper}`;
  }) ?? [];
  const chartTitle = t("overview.chartLabel", { subject: t(`subjects.${subject}`) });
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
    colors: ["#465fff"],
    plotOptions: {
      bar: {
        horizontal: false,
        columnWidth: "55%",
        borderRadius: 3,
        borderRadiusApplication: "end",
        dataLabels: { position: "top" },
      },
    },
    dataLabels: {
      enabled: true,
      formatter: (value) => countFormatter.format(Number(value)),
      offsetY: -24,
      style: {
        fontSize: "12px",
        fontWeight: 500,
        colors: [theme === "dark" ? "#98a2b3" : "#667085"],
      },
      background: { enabled: false },
    },
    legend: { show: false },
    xaxis: {
      categories: intervalLabels,
      axisBorder: { show: false },
      axisTicks: { show: false },
      labels: { rotate: -45, trim: false, hideOverlappingLabels: false },
    },
    yaxis: {
      min: 0,
      decimalsInFloat: 0,
      forceNiceScale: true,
      labels: { formatter: (value) => countFormatter.format(value) },
    },
    grid: {
      borderColor: theme === "dark" ? "#344054" : "#eaecf0",
      padding: { top: 20 },
    },
    fill: { opacity: 1 },
    tooltip: { theme, y: { formatter: (value) => countFormatter.format(value) } },
  };

  return (
    <div className="min-w-0 space-y-6">
      <PageMeta title={t("overview.metaTitle")} description={t("overview.metaDescription")} />
      <div>
        <h1 className="text-2xl font-semibold text-gray-800 dark:text-white/90">{t("overview.title")}</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{t("overview.description")}</p>
      </div>

      <section
        aria-labelledby="score-overview-title"
        aria-busy={resource.loading}
        className="min-w-0 rounded-2xl border border-gray-200 bg-white p-5 sm:p-6 dark:border-gray-800 dark:bg-gray-900"
      >
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 id="score-overview-title" className="text-lg font-semibold text-gray-800 dark:text-white/90">
              {t("overview.distributionTitle")}
            </h2>
          </div>
          <div className="w-full shrink-0 sm:w-48">
            <label htmlFor="overview-subject" className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">
              {t("overview.subject")}
            </label>
            <select
              id="overview-subject"
              value={subject}
              onChange={(event) => setSubject(event.target.value as ScoreSubject)}
              className="h-11 w-full rounded-lg border border-gray-300 bg-white px-3 text-sm text-gray-800 focus:border-brand-300 focus:outline-2 focus:outline-brand-500 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90"
            >
              {scoreColumns.map((column) => (
                <option key={column.key} value={column.key}>{t(column.labelKey)}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="mt-5" aria-live="polite">
          {resource.loading && (
            <p role="status" className="text-sm text-gray-500 dark:text-gray-400">{t("overview.loading")}</p>
          )}
          {resource.error && (
            <div role="alert" className="rounded-xl border border-error-500/30 bg-error-500/5 p-4">
              <h3 className="text-sm font-semibold text-gray-800 dark:text-white/90">
                {t(resource.error.kind === "timeout" ? "errors.timeout.title" : resource.error.kind === "network" ? "errors.network.title" : "overview.errorTitle")}
              </h3>
              <p className="mt-1 text-sm text-gray-700 dark:text-gray-300">
                {t(resource.error.kind === "timeout" ? "errors.timeout.message" : resource.error.kind === "network" ? "errors.network.message" : "report.errorMessage")}
              </p>
              <Button
                size="sm"
                variant="outline"
                onClick={resource.refetch}
                className="mt-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500"
              >
                {t("errors.retry")}
              </Button>
            </div>
          )}
          {data && (
            <>
              <dl className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-800 dark:bg-gray-800/50">
                  <dt className="text-sm text-gray-500 dark:text-gray-400">{t("overview.totalStudents")}</dt>
                  <dd className="mt-1 text-xl font-semibold tabular-nums text-gray-800 dark:text-white/90">{countFormatter.format(data.totalStudents)}</dd>
                </div>
                <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-800 dark:bg-gray-800/50">
                  <dt className="text-sm text-gray-500 dark:text-gray-400">{t("overview.averageScore")}</dt>
                  <dd className="mt-1 text-xl font-semibold tabular-nums text-gray-800 dark:text-white/90">
                    {data.averageScore === null ? t("overview.unavailable") : formatScore(data.averageScore, language)}
                  </dd>
                </div>
                <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-800 dark:bg-gray-800/50">
                  <dt className="text-sm text-gray-500 dark:text-gray-400">{t("overview.medianScore")}</dt>
                  <dd className="mt-1 text-xl font-semibold tabular-nums text-gray-800 dark:text-white/90">
                    {data.medianScore === null ? t("overview.unavailable") : formatScore(data.medianScore, language)}
                  </dd>
                </div>
              </dl>

              {data.totalStudents === 0 ? (
                <p role="status" className="mt-5 text-sm text-gray-500 dark:text-gray-400">
                  {t("overview.empty")}
                </p>
              ) : (
                <section aria-labelledby="score-histogram-title" className="mt-6 min-w-0">
                  <h3 id="score-histogram-title" className="text-base font-semibold text-gray-800 dark:text-white/90">
                    {t("overview.histogramTitle")}
                  </h3>
                  <div
                    role="region"
                    aria-label={chartTitle}
                    tabIndex={0}
                    className="mt-2 min-w-0 overflow-x-auto rounded-lg focus-visible:outline-2 focus-visible:outline-brand-500 xl:overflow-x-visible"
                  >
                    <div className="min-w-[600px] xl:min-w-0" role="img" aria-label={chartTitle}>
                      <Suspense fallback={<p role="status" className="py-6 text-sm text-gray-500 dark:text-gray-400">{t("overview.loadingChart")}</p>}>
                        <Chart
                          options={options}
                          series={[{ name: t("overview.students"), data: data.bins.map((bin) => bin.count) }]}
                          type="bar"
                          height={340}
                          width="100%"
                        />
                      </Suspense>
                    </div>
                  </div>
                </section>
              )}

            </>
          )}
        </div>
      </section>
    </div>
  );
}
