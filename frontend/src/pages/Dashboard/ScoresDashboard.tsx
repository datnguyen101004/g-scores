import { useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import PageMeta from "@/components/common/PageMeta";
import ApiErrorNotice from "@/components/scores/ApiErrorNotice";
import StudentDetails from "@/components/scores/StudentDetails";
import Button from "@/components/ui/button/Button";
import { useStudent } from "@/hooks/useStudent";

const inputClass = "h-11 rounded-lg border border-gray-300 bg-transparent px-3 text-sm text-gray-800 outline-none focus:border-brand-500 focus:ring-3 focus:ring-brand-500/10 disabled:opacity-50 dark:border-gray-700 dark:text-white/90";
const focusClass = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500";

export default function ScoresDashboard() {
  const { t } = useTranslation("scores");
  const sbdInputRef = useRef<HTMLInputElement>(null);
  const [sbdInput, setSbdInput] = useState("");
  const [submittedSbd, setSubmittedSbd] = useState<string | null>(null);
  const [searchError, setSearchError] = useState<"required" | null>(null);
  const lookup = useStudent(submittedSbd);

  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const sbd = sbdInput.trim();
    if (!sbd) {
      setSearchError("required");
      sbdInputRef.current?.focus();
      return;
    }
    setSearchError(null);
    if (sbd === submittedSbd) lookup.refetch();
    else setSubmittedSbd(sbd);
  }

  function clearSearch() {
    setSbdInput("");
    setSubmittedSbd(null);
    setSearchError(null);
  }

  return (
    <>
      <PageMeta title={t("page.metaTitle")} description={t("page.metaDescription")} />
      <div className="min-w-0 space-y-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-gray-800 dark:text-white/90">{t("page.title")}</h1>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{t("page.subtitle")}</p>
          </div>
        </div>

        <section aria-labelledby="lookup-title" className="rounded-2xl border border-gray-200 bg-white p-5 sm:p-6 dark:border-gray-800 dark:bg-gray-900">
          <h2 id="lookup-title" className="text-lg font-semibold text-gray-800 dark:text-white/90">{t("page.lookupTitle")}</h2>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{t("page.lookupIntro")}</p>
          <form onSubmit={search} className="mt-5 flex flex-wrap items-end gap-3">
            <div className="w-full sm:max-w-80">
              <label htmlFor="sbd" className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">{t("page.registrationNumber")}</label>
              <input ref={sbdInputRef} id="sbd" name="sbd" type="text" inputMode="numeric" autoComplete="off" value={sbdInput} onChange={(event) => setSbdInput(event.target.value)} placeholder={t("page.registrationNumberPlaceholder")} aria-invalid={searchError ? true : undefined} aria-describedby={searchError ? "search-error" : undefined} className={`${inputClass} w-full`} />
            </div>
            <Button size="sm" disabled={lookup.loading} className={focusClass}>{lookup.loading ? t("page.loadingAction") : t("page.lookupAction")}</Button>
            {(sbdInput || submittedSbd) && <button type="button" onClick={clearSearch} className={`h-11 rounded-lg px-4 text-sm font-medium text-gray-600 hover:bg-gray-50 dark:text-gray-400 dark:hover:bg-gray-800 ${focusClass}`}>{t("page.clearSearch")}</button>}
          </form>
          {searchError && <p id="search-error" role="alert" className="mt-3 text-sm text-error-600 dark:text-error-400">{t("validation.required")}</p>}
          <div aria-live="polite" aria-busy={lookup.loading}>
            {lookup.loading && <p role="status" className="mt-5 text-sm text-gray-500 dark:text-gray-400">{t("page.loadingScores")}</p>}
            {lookup.error && <div className="mt-5"><ApiErrorNotice error={lookup.error} onRetry={lookup.refetch} /></div>}
            {lookup.data && <StudentDetails student={lookup.data} />}
          </div>
        </section>
      </div>
    </>
  );
}
