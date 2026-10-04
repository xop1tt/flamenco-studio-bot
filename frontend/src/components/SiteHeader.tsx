import { getCurrentUser } from "@/lib/auth";
import { logoutAction } from "@/lib/actions";
import Link from "next/link";
import { NAV_ITEM_CLASS, PRIMARY_BUTTON_CLASS } from "@/lib/glass";
import { NavLink } from "./NavLink";
import { MobileNav } from "./MobileNav";
import { ThemeToggle } from "./ThemeToggle";

const NAV_LINKS = [
  { href: "/schedule", label: "Расписание" },
  { href: "/packages", label: "Абонементы" },
  { href: "/contact", label: "Контакты" },
];

export async function SiteHeader() {
  const currentUser = await getCurrentUser();

  const authSection = currentUser ? (
    <form action={logoutAction} className="flex flex-col items-start gap-1 md:flex-row md:items-center md:gap-2">
      <NavLink href="/account">{currentUser.display_name}</NavLink>
      <button type="submit" className={`${NAV_ITEM_CLASS} text-[var(--text-secondary)] hover:text-[var(--primary)]`}>
        Выйти
      </button>
    </form>
  ) : (
    <Link
      href="/login"
      className={`${PRIMARY_BUTTON_CLASS} whitespace-nowrap px-4 py-2 text-base leading-none lg:px-5 lg:text-[18px]`}
    >
      Войти
    </Link>
  );

  return (
    // Шапка — плавающая стеклянная панель (.site-header-bar, globals.css)
    // с отступом от краёв экрана; .site-header вокруг неё прозрачен и не
    // ловит клики. Плотность стекла растёт с прокруткой, лого и "Войти"
    // сворачиваются — оба параметра пишет GlassController. На главной
    // шапка лежит поверх сцены, не сдвигая её (см. body:has(.scenes)).
    <header className="site-header">
      {/* header-logo/header-cta — сворачиваются при скролле вниз, см.
          globals.css (--header-collapse, пишет GlassController). Панель
          шириной по содержимому (w-fit) и по центру: при сворачивании она
          непрерывно сужается вокруг навигации, а не остаётся широкой
          плашкой с пустым краем. ThemeToggle намеренно вне этой группы —
          не участвует в сворачивании. */}
      <div className="site-header-bar header-row mx-auto flex w-fit max-w-full items-center gap-2 px-2.5 sm:max-w-5xl sm:gap-3 sm:px-4">
        <Link
          href="/"
          className="header-logo font-heading min-w-0 text-ellipsis whitespace-nowrap text-[17px] font-bold tracking-wide text-[var(--accent-dark)] sm:text-[20px] md:shrink-0 lg:text-[24px]"
        >
          Mirada Studio
        </Link>

        {/* Полное меню — только от md и шире. На мобильном оно переносилось в
            несколько строк и съедало четверть экрана, поэтому ниже есть
            отдельная компактная версия. */}
        <nav className="header-nav ml-auto hidden items-center gap-2 md:flex">
          {NAV_LINKS.map((link) => (
            <NavLink key={link.href} href={link.href}>
              {link.label}
            </NavLink>
          ))}
        </nav>

        {/* ThemeToggle — сосед header-cta в одной группе (а не отдельный
            flex-item): при схлопывании "Войти" тема лишь плавно смещается
            на освобождающуюся ширину, а не прыгает самостоятельно —
            визуально остаётся "в углу". */}
        <div className="header-right hidden items-center gap-3 md:flex">
          <div className="header-cta overflow-hidden">{authSection}</div>
          <ThemeToggle />
        </div>

        {/* Компактная шапка на мобильном: лого + кнопка записи + тема + меню-иконка. */}
        <div className="ml-auto flex shrink-0 items-center gap-1.5 md:hidden">
          <Link
            href="/schedule"
            className={`${PRIMARY_BUTTON_CLASS} whitespace-nowrap px-3.5 py-2 text-sm leading-none`}
          >
            Записаться
          </Link>
          <ThemeToggle />
          <MobileNav links={NAV_LINKS}>
            <div className="mt-2 border-t border-[var(--border)] pt-2">{authSection}</div>
          </MobileNav>
        </div>
      </div>
    </header>
  );
}
