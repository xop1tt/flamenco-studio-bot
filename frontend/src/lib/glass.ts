// Общие наборы классов glass design system (см. globals.css). Отдельный
// не-клиентский модуль: строки отсюда нужны и серверным компонентам
// (SiteHeader), и клиентским (NavLink).

// Навигация: subtle-стекло в режиме ghost — проявляется на hover/focus и на
// текущей странице. inline-flex + items-center центрируют текст по боксу.
export const NAV_ITEM_CLASS =
  "glass-subtle glass-interactive glass-ghost inline-flex items-center justify-center rounded-full px-3 py-1.5 text-[18px] font-semibold leading-none";

// Вторичная кнопка/ссылка: subtle-стекло с полным набором состояний. Размеры
// (padding, шрифт) задаёт вызывающий — они у кнопок разные.
export const GLASS_BUTTON_CLASS =
  "glass-subtle glass-interactive rounded-full font-medium hover:text-[var(--primary)]";
