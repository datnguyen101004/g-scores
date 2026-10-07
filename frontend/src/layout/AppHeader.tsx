import { useTranslation } from "react-i18next";
import { useSidebar } from "@/context/SidebarContext";
import { useLocation } from "react-router";

export default function AppHeader() {
  const { isMobileOpen, toggleMobileSidebar } = useSidebar();
  const { t } = useTranslation("common");
  const { pathname } = useLocation();
  const menuLabel = t(isMobileOpen ? "app.sidebar.closeMenu" : "app.sidebar.openMenu");

  return (
    <header className="sticky top-0 z-30 border-b border-gray-200 bg-white xl:hidden dark:border-gray-800 dark:bg-gray-900">
      <div className="flex items-center gap-2 px-3 py-3 sm:px-4">
        <button
          type="button"
          onClick={toggleMobileSidebar}
          aria-controls="app-sidebar"
          aria-expanded={isMobileOpen}
          aria-label={menuLabel}
          title={menuLabel}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-100 focus-visible:outline-2 focus-visible:outline-brand-500 dark:border-gray-800 dark:text-gray-400 dark:hover:bg-gray-800"
        >
          <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <path d={isMobileOpen ? "m6 6 12 12M18 6 6 18" : "M4 6h16M4 12h16M4 18h16"} />
          </svg>
        </button>
        <h2 className="truncate text-lg font-medium text-gray-800 dark:text-white/90">{t(pathname === "/report" ? "app.sidebar.report" : pathname === "/overview" ? "app.sidebar.overview" : "app.sidebar.dashboard")}</h2>
      </div>
    </header>
  );
}
