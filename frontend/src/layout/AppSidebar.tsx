import { useTranslation } from "react-i18next";
import { useSidebar } from "@/context/SidebarContext";
import LanguageDropdown from "@/components/header/LanguageDropdown";
import { ThemeToggleButton } from "@/components/common/ThemeToggleButton";
import { useEffect, useRef } from "react";
import { Link, useLocation } from "react-router";
import { GridIcon } from "../icons";
import { cn } from "../utils";

const AppSidebar = () => {
  const { isExpanded, isHovered, isMobileOpen, setIsHovered, setIsMobileOpen } =
    useSidebar();
  const location = useLocation();
  const { t } = useTranslation("common");
  const isSidebarExpanded = isExpanded || isHovered || isMobileOpen;
  const isOverviewActive = location.pathname === "/overview";
  const isDashboardActive = location.pathname === "/";
  const isReportActive = location.pathname === "/report";
  const sidebarRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!isMobileOpen) {
      return;
    }

    const sidebar = sidebarRef.current;
    const opener = document.querySelector<HTMLButtonElement>('button[aria-controls="app-sidebar"]');
    const closeMobileSidebar = () => setIsMobileOpen(false);
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeMobileSidebar();
        return;
      }
      if (event.key !== "Tab" || !sidebar) return;

      const focusable = Array.from(
        sidebar.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'),
      ).filter((element) => element.getClientRects().length > 0);
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (!first || !last) return;

      const outside = !sidebar.contains(document.activeElement);
      if (event.shiftKey && (document.activeElement === first || outside)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || outside)) {
        event.preventDefault();
        first.focus();
      }
    };

    closeButtonRef.current?.focus();
    window.addEventListener("popstate", closeMobileSidebar);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("popstate", closeMobileSidebar);
      document.removeEventListener("keydown", handleKeyDown);
      if (opener?.getClientRects().length) opener.focus();
    };
  }, [isMobileOpen, setIsMobileOpen]);

  const closeMobileSidebarOnNavigate = () => {
    if (isMobileOpen) {
      setIsMobileOpen(false);
    }
  };

  return (
    <div
      ref={sidebarRef}
      id="app-sidebar"
      role={isMobileOpen ? "dialog" : "complementary"}
      aria-modal={isMobileOpen ? true : undefined}
      aria-label={t("app.sidebar.navigationLabel")}
      className={cn(
        "fixed inset-s-0 top-0 z-50 h-dvh flex-col border-e border-gray-200 bg-white px-5 text-gray-900 transition-all duration-300 ease-in-out xl:translate-x-0 xl:rtl:translate-x-0 dark:border-gray-800 dark:bg-gray-900",
        isSidebarExpanded ? "w-72.5" : "w-22.5",
        isMobileOpen
          ? "flex translate-x-0"
          : "hidden -translate-x-full xl:flex rtl:translate-x-full",
      )}
      onMouseEnter={() => {
        if (!isExpanded && !isMobileOpen) {
          setIsHovered(true);
        }
      }}
      onMouseLeave={() => setIsHovered(false)}
    >
      <div
        className={cn(
          "flex shrink-0 items-center gap-2 py-6",
          isSidebarExpanded ? "justify-start" : "xl:justify-center",
        )}
      >
        <Link
          to="/"
          onClick={closeMobileSidebarOnNavigate}
          aria-label={t("app.sidebar.brandLinkLabel")}
          className="flex items-center gap-3"
        >
          <span
            aria-hidden="true"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-500 text-sm font-bold text-white shadow-theme-xs"
          >
            G
          </span>
          {isSidebarExpanded && (
            <span className="flex flex-col leading-tight">
              <span className="text-base font-semibold text-gray-900 dark:text-white">
                G-Scores
              </span>
              <span className="text-xs text-gray-500 dark:text-gray-400">
                {t("app.sidebar.brandDescription")}
              </span>
            </span>
          )}
        </Link>
        <button
          ref={closeButtonRef}
          type="button"
          aria-label={t("app.sidebar.closeMenu")}
          onClick={() => setIsMobileOpen(false)}
          className="ml-auto flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100 focus-visible:outline-2 focus-visible:outline-brand-500 xl:hidden dark:text-gray-400 dark:hover:bg-gray-800"
        >
          <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <path d="m6 6 12 12M18 6 6 18" />
          </svg>
        </button>
      </div>

      <div className="no-scrollbar flex flex-1 flex-col overflow-y-auto">
        <nav aria-label={t("app.sidebar.primaryNavigation")}>
          <ul className="flex flex-col gap-1">
            <li>
              <Link
                to="/overview"
                onClick={closeMobileSidebarOnNavigate}
                aria-current={isOverviewActive ? "page" : undefined}
                aria-label={t("app.sidebar.overview")}
                title={t("app.sidebar.overview")}
                className={`group menu-item ${isOverviewActive ? "menu-item-active" : "menu-item-inactive"} ${isSidebarExpanded ? "xl:justify-start" : "xl:justify-center"}`}
              >
                <span className={`menu-item-icon-size ${isOverviewActive ? "menu-item-icon-active" : "menu-item-icon-inactive"}`}>
                  <svg aria-hidden="true" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                    <path d="M10 4a9 9 0 1 0 9 9h-9V4Z" />
                    <path d="M14 2a8 8 0 0 1 8 8h-8V2Z" />
                  </svg>
                </span>
                {isSidebarExpanded && <span className="menu-item-text">{t("app.sidebar.overview")}</span>}
              </Link>
            </li>
            <li>
              <Link
                to="/"
                onClick={closeMobileSidebarOnNavigate}
                aria-current={isDashboardActive ? "page" : undefined}
                aria-label={t("app.sidebar.dashboard")}
                title={t("app.sidebar.dashboard")}
                className={`group menu-item ${
                  isDashboardActive ? "menu-item-active" : "menu-item-inactive"
                } ${
                  isSidebarExpanded ? "xl:justify-start" : "xl:justify-center"
                }`}
              >
                <span
                  className={`menu-item-icon-size ${
                    isDashboardActive
                      ? "menu-item-icon-active"
                      : "menu-item-icon-inactive"
                  }`}
                >
                  <GridIcon fontSize={24} />
                </span>
                {isSidebarExpanded && (
                  <span className="menu-item-text">{t("app.sidebar.dashboard")}</span>
                )}
              </Link>
            </li>
            <li>
              <Link
                to="/report"
                onClick={closeMobileSidebarOnNavigate}
                aria-current={isReportActive ? "page" : undefined}
                aria-label={t("app.sidebar.report")}
                title={t("app.sidebar.report")}
                className={`group menu-item ${isReportActive ? "menu-item-active" : "menu-item-inactive"} ${isSidebarExpanded ? "xl:justify-start" : "xl:justify-center"}`}
              >
                <span className={`menu-item-icon-size ${isReportActive ? "menu-item-icon-active" : "menu-item-icon-inactive"}`}>
                  <svg aria-hidden="true" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                    <path d="M4 20h16M7 16V9m5 7V4m5 12v-5" />
                  </svg>
                </span>
                {isSidebarExpanded && <span className="menu-item-text">{t("app.sidebar.report")}</span>}
              </Link>
            </li>
          </ul>
        </nav>
      </div>
      <div className={cn(
        "mt-auto flex shrink-0 items-center gap-2 border-t border-gray-200 py-4 dark:border-gray-800",
        isSidebarExpanded ? "justify-between" : "flex-col",
      )}>
        <LanguageDropdown compact={!isSidebarExpanded} />
        <ThemeToggleButton />
      </div>
    </div>
  );
};

export default AppSidebar;
