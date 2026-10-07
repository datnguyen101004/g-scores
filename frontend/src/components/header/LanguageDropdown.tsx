import { useRef, useState, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { useLanguage } from "@/context/LanguageContext";
import { useClickOutside } from "@/hooks/useClickOutside";

export default function LanguageDropdown({ compact = false }: { compact?: boolean }) {
  const { t } = useTranslation("common");
  const { language, currentLanguage, availableLanguages, setLanguage } = useLanguage();
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  useClickOutside(containerRef, () => setIsOpen(false));

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape" && isOpen) {
      event.preventDefault();
      event.stopPropagation();
      setIsOpen(false);
      triggerRef.current?.focus();
      return;
    }
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const key = event.key;
    const focusOption = () => {
      const options = containerRef.current?.querySelectorAll<HTMLButtonElement>("[role='menuitemradio']");
      if (!options?.length) return;
      const index = Array.from(options).indexOf(document.activeElement as HTMLButtonElement);
      const next = key === "Home" ? 0 : key === "End" ? options.length - 1
        : key === "ArrowUp" ? (index <= 0 ? options.length - 1 : index - 1)
          : (index + 1) % options.length;
      options[next].focus();
    };
    if (isOpen) focusOption();
    else {
      setIsOpen(true);
      requestAnimationFrame(focusOption);
    }
  }

  return (
    <div
      ref={containerRef}
      className="relative shrink-0"
      onPointerEnter={(event) => { if (event.pointerType === "mouse") setIsOpen(true); }}
      onPointerLeave={(event) => { if (event.pointerType === "mouse") setIsOpen(false); }}
      onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setIsOpen(false); }}
      onKeyDown={handleKeyDown}
    >
      <button
        ref={triggerRef}
        id="language-select"
        type="button"
        aria-label={`${t("app.language")}: ${currentLanguage.name}`}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-controls={isOpen ? "language-menu" : undefined}
        onClick={() => setIsOpen(true)}
        className="inline-flex h-8 items-center gap-1 rounded-lg bg-transparent px-1.5 text-sm font-normal text-gray-700 transition-colors hover:text-gray-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500 dark:text-gray-300 dark:hover:text-white"
      >
        <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
          <circle cx="12" cy="12" r="9" />
          <ellipse cx="12" cy="12" rx="4" ry="9" />
          <path d="M3 12h18" />
        </svg>
        {!compact && <span>{currentLanguage.name}</span>}
        {!compact && <svg aria-hidden="true" width="12" height="12" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" className={`transition-transform ${isOpen ? "rotate-180" : ""}`}>
          <path d="m5 7 5 5 5-5" />
        </svg>}
      </button>
      {isOpen && (
        <div className="absolute bottom-full left-0 z-50 min-w-32 pb-1">
          <div id="language-menu" role="menu" aria-label={t("app.language")} className="overflow-hidden rounded-lg border border-gray-100 bg-white py-1 shadow-theme-lg dark:border-gray-700 dark:bg-gray-800">
            {availableLanguages.map(({ code, name }) => (
              <button
                key={code}
                type="button"
                role="menuitemradio"
                aria-checked={language === code}
                onClick={() => {
                  setLanguage(code);
                  setIsOpen(false);
                  triggerRef.current?.focus();
                }}
                className={`block w-full px-3 py-2 text-left text-sm font-normal hover:bg-gray-50 focus-visible:bg-gray-50 focus-visible:outline-none dark:hover:bg-gray-700 dark:focus-visible:bg-gray-700 ${language === code ? "text-brand-500 dark:text-brand-400" : "text-gray-800 dark:text-gray-200"}`}
              >
                {name}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
