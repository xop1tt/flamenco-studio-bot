// Общая логика темы. Выбор пользователя хранится в localStorage, а React
// синхронизируется с ним через useSyncExternalStore (см. ThemeToggle) —
// это даёт корректную гидратацию без ручного "mounted"-эффекта и без
// setState при маунте (react-hooks/set-state-in-effect).
//
// No-flash скрипт в layout.tsx продублирован как обычный <script>, так как
// должен выполняться синхронно до гидратации и не может импортировать этот
// модуль.

export type ThemePreference = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

export const THEME_STORAGE_KEY = "theme";

export function getSystemTheme(): ResolvedTheme {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function resolveTheme(preference: ThemePreference): ResolvedTheme {
  return preference === "system" ? getSystemTheme() : preference;
}

export function applyTheme(preference: ThemePreference) {
  document.documentElement.setAttribute("data-theme", resolveTheme(preference));
}

function readStoredPreference(): ThemePreference {
  const stored = localStorage.getItem(THEME_STORAGE_KEY);
  return stored === "light" || stored === "dark" ? stored : "system";
}

const listeners = new Set<() => void>();

function notifyListeners() {
  listeners.forEach((listener) => listener());
}

/** useSyncExternalStore subscribe: уведомляет о смене темы в этой вкладке
 *  (через setThemePreference) и в других вкладках (storage-событие). */
export function subscribeThemePreference(callback: () => void) {
  listeners.add(callback);
  const onStorage = (event: StorageEvent) => {
    if (event.key === THEME_STORAGE_KEY) callback();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(callback);
    window.removeEventListener("storage", onStorage);
  };
}

export function getThemePreference(): ThemePreference {
  return readStoredPreference();
}

// До гидратации предпочтение из localStorage недоступно — отдаём "system"
// как снимок сервера. useSyncExternalStore сам гарантирует, что первый
// клиентский рендер совпадёт с этим значением, и только после гидратации
// переключится на реальное — без предупреждений о рассинхронизации разметки.
export function getServerThemePreference(): ThemePreference {
  return "system";
}

export function setThemePreference(preference: ThemePreference) {
  localStorage.setItem(THEME_STORAGE_KEY, preference);
  applyTheme(preference);
  notifyListeners();
}
