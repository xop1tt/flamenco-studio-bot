// Общие наборы классов glass design system (см. globals.css). Отдельный
// не-клиентский модуль: строки отсюда нужны и серверным компонентам
// (SiteHeader), и клиентским (NavLink).

// Навигация: subtle-стекло в режиме ghost — проявляется на hover/focus и на
// текущей странице. inline-flex + items-center центрируют текст по боксу.
export const NAV_ITEM_CLASS =
  "glass-subtle glass-interactive glass-ghost inline-flex items-center justify-center whitespace-nowrap rounded-full px-3 py-1.5 text-[18px] font-semibold leading-none md:px-2.5 md:text-base lg:px-3 lg:text-[18px]";

// Вторичная кнопка/ссылка: прозрачное стекло с тонкой кромкой; на hover
// кромка ярче и появляется внутренний блик, без свечения вокруг. Размеры
// (padding, шрифт) задаёт вызывающий — они у кнопок разные. Над живым фоном
// (сцена главной) добавлять glass-float — включает размытие подложки.
export const GLASS_BUTTON_CLASS =
  "glass-subtle glass-interactive inline-flex items-center justify-center rounded-full font-medium";

// Основное действие: то же жидкое стекло, но тонированное бордовым
// (.btn-primary). Размеры задаёт вызывающий.
export const PRIMARY_BUTTON_CLASS =
  "btn-primary rounded-full font-semibold";
