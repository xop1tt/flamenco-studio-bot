"use client";

import { useEffect, useSyncExternalStore } from "react";
import {
  applyTheme,
  getResolvedThemeSnapshot,
  getServerResolvedTheme,
  getServerThemePreference,
  getThemePreference,
  setThemePreference,
  subscribeResolvedTheme,
  subscribeThemePreference,
  type ResolvedTheme,
} from "@/lib/theme";

const LABELS: Record<ResolvedTheme, string> = {
  light: "Светлая тема",
  dark: "Тёмная тема",
};

function ThemeIcon({ resolved }: { resolved: ResolvedTheme }) {
  if (resolved === "light") {
    return (
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <circle cx="12" cy="12" r="4.5" />
        <path d="M12 2.5v2.5M12 19v2.5M4.6 4.6l1.8 1.8M17.6 17.6l1.8 1.8M2.5 12H5M19 12h2.5M4.6 19.4l1.8-1.8M17.6 6.4l1.8-1.8" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a6.8 6.8 0 0 0 10.5 10.5Z" />
    </svg>
  );
}

// Переключатель темы: только два явных состояния — светлая/тёмная, без
// отдельного пункта «как на устройстве» в самом переключателе. Системная
// тема остаётся поведением по умолчанию до первого клика (см.
// THEME_INIT_SCRIPT в layout.tsx и resolveTheme в lib/theme.ts — preference
// "system" там никуда не делась, просто кнопка больше не предлагает выбрать
// её явно и всегда переключает между light/dark).
export function ThemeToggle() {
  const preference = useSyncExternalStore(
    subscribeThemePreference,
    getThemePreference,
    getServerThemePreference,
  );
  // Отдельный стор, а не resolveTheme(preference) прямо в рендере — см.
  // комментарий у getResolvedThemeSnapshot в lib/theme.ts (иначе hydration
  // mismatch на системной тёмной теме).
  const resolved = useSyncExternalStore(
    subscribeResolvedTheme,
    getResolvedThemeSnapshot,
    getServerResolvedTheme,
  );

  // Пока пользователь ещё не кликал (preference === "system"), следим за
  // изменением настройки ОС и сразу применяем её к <html>.
  useEffect(() => {
    if (preference !== "system") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => applyTheme("system");
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [preference]);

  function toggle() {
    setThemePreference(resolved === "dark" ? "light" : "dark");
  }

  const label = LABELS[resolved];

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={`Тема оформления: ${label}. Нажмите, чтобы переключить.`}
      title={label}
      // До гидратации resolved всегда "light" (на сервере нет window),
      // поэтому подпись может на долю секунды отличаться от финальной —
      // ожидаемо и безопасно, гасим предупреждение React об этом.
      suppressHydrationWarning
      className="glass-subtle glass-interactive flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-[var(--text-primary)] hover:text-[var(--primary)]"
    >
      <ThemeIcon resolved={resolved} />
    </button>
  );
}
