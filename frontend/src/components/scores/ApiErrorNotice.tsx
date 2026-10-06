import { useTranslation } from "react-i18next";
import Button from "@/components/ui/button/Button";
import type { ApiError } from "@/types/student";

export default function ApiErrorNotice({
  error,
  onRetry,
}: {
  error: ApiError;
  onRetry?: () => void;
}) {
  const { t } = useTranslation("scores");
  const notFound = error.statusCode === 404;
  const errorKind = notFound ? "notFound" : error.statusCode === null ? "network" : "server";

  return (
    <div role="alert" className="rounded-xl border border-warning-500 bg-warning-50 p-4 dark:border-warning-500/30 dark:bg-warning-500/15">
      <p className="text-sm font-semibold text-gray-800 dark:text-white/90">
        {t(`errors.${errorKind}.title`)}
      </p>
      <p className="mt-1 break-words text-sm text-gray-700 dark:text-gray-300">{t(`errors.${errorKind}.message`)}</p>
      {!notFound && onRetry && (
        <Button size="sm" variant="outline" onClick={onRetry} className="mt-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500">
          {t("errors.retry")}
        </Button>
      )}
    </div>
  );
}

