import { useTranslation } from "react-i18next";
import GridShape from "@/components/common/GridShape";
import PageMeta from "@/components/common/PageMeta";
import { cn } from "@/utils";
import { Link } from "react-router";

interface NotFoundProps {
  className?: string;
}

export default function NotFound({ className }: NotFoundProps) {
  const { t } = useTranslation("common");
  return (
    <>
      <PageMeta
        title={t("app.notFound.title")}
        description={t("app.notFound.description")}
      />
      <div
        className={cn(
          "relative z-1 flex min-h-screen flex-col items-center justify-center overflow-hidden p-6",
          className,
        )}
      >
        <GridShape />
        <div className="mx-auto w-full max-w-60.5 text-center sm:max-w-118">
          <h1 className="mb-8 text-title-md font-bold text-gray-800 xl:text-title-2xl dark:text-white/90">
            {t("app.notFound.heading")}
          </h1>

          <img
            src="/images/error/404.svg"
            alt={t("app.notFound.imageAlt")}
            className="dark:hidden"
          />
          <img
            src="/images/error/404-dark.svg"
            alt={t("app.notFound.imageAlt")}
            className="hidden dark:block"
          />

          <p className="mt-10 mb-6 text-base text-gray-700 sm:text-lg dark:text-gray-400">
            {t("app.notFound.message")}
          </p>

          <Link
            to="/"
            className={cn(
              "inline-flex items-center justify-center rounded-lg border border-gray-300 bg-white px-5 py-3.5 text-sm font-medium text-gray-700 shadow-theme-xs hover:bg-gray-50 hover:text-gray-800 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-white/3 dark:hover:text-gray-200",
            )}
          >
            {t("app.notFound.backHome")}
          </Link>
        </div>
        {/* <!-- Footer --> */}
        <p
          className={cn(
            "absolute inset-s-1/2 bottom-6 -translate-x-1/2 text-center text-sm text-gray-500 rtl:translate-x-1/2 dark:text-gray-400",
          )}
        >
          {t("app.copyright", { year: new Date().getFullYear() })}
        </p>
      </div>
    </>
  );
}
