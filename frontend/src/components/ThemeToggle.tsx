"use client";

import { useEffect, useSyncExternalStore } from "react";
import {
  applyTheme,
  getServerThemePreference,
  getSystemTheme,
  getThemePreference,
  setThemePreference,
  subscribeThemePreference,
  type ThemePreference,
} from "@/lib/theme";

const LABELS: Record<ThemePreference, string> = {
  light: "Светлая тема",
  dark: "Тёмная тема",
  system: "Системная тема",
};

const NEXT_PREFERENCE: Record<ThemePreference, ThemePreference> = {
  light: "dark",
  dark: "system",
  system: "light",
};

function ThemeIcon({ preference }: { preference: ThemePreference }) {
  if (preference === "light") {
    return (
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <circle cx="12" cy="12" r="4.5" />
        <path d="M12 2.5v2.5M12 19v2.5M4.6 4.6l1.8 1.8M17.6 17.6l1.8 1.8M2.5 12H5M19 12h2.5M4.6 19.4l1.8-1.8M17.6 6.4l1.8-1.8" />
      </svg>
    );
  }
  if (preference === "dark") {
    return (
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a6.8 6.8 0 0 0 10.5 10.5Z" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="4.5" width="18" height="12" rx="1.5" />
      <path d="M8.5 20h7M12 16.5V20" />
    </svg>
  );
}

// Переключатель темы: три состояния по кругу (светлая → тёмная →
// системная → ...). Предпочтение читается из localStorage через
// useSyncExternalStore — на сервере и при первом клиентском рендере это
// всегда "system" (см. getServerThemePreference), а сразу после гидратации
// React сам подставляет настоящее значение, без ручного мигания и без
// setState в эффекте на маунте.
export function ThemeToggle() {
  const preference = useSyncExternalStore(
    subscribeThemePreference,
    getThemePreference,
    getServerThemePreference,
  );

  // Пока открыта «системная» тема, следим за изменением настройки ОС и
  // сразу применяем её к <html> — без ожидания перезагрузки страницы.
  useEffect(() => {
    if (preference !== "system") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => applyTheme("system");
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [preference]);

  function cycle() {
    setThemePreference(NEXT_PREFERENCE[preference]);
  }

  const systemGuess =
    typeof window !== "undefined" && getSystemTheme() === "dark" ? "тёмная" : "светлая";
  const label =
    preference === "system" ? `${LABELS.system} (сейчас ${systemGuess})` : LABELS[preference];

  return (
    <button
      type="button"
      onClick={cycle}
      aria-label={`Тема оформления: ${label}. Нажмите, чтобы переключить.`}
      title={label}
      // До гидратации systemGuess всегда "светлая" (на сервере нет window),
      // поэтому подпись может на долю секунды отличаться от финальной —
      // ожидаемо и безопасно, гасим предупреждение React об этом.
      suppressHydrationWarning
      className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-[var(--border-strong)] bg-[var(--surface)] text-[var(--text-primary)] transition hover:border-[var(--primary)] hover:text-[var(--primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--surface)]"
    >
      <ThemeIcon preference={preference} />
    </button>
  );
}
