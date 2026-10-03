import { getCurrentUser } from "@/lib/auth";
import { logoutAction } from "@/lib/actions";
import Link from "next/link";
import { NAV_ITEM_CLASS } from "@/lib/glass";
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
    <form action={logoutAction} className="flex flex-col items-start gap-1 sm:flex-row sm:items-center sm:gap-2">
      <NavLink href="/account">{currentUser.display_name}</NavLink>
      <button type="submit" className={`${NAV_ITEM_CLASS} text-[var(--text-secondary)] hover:text-[var(--primary)]`}>
        Выйти
      </button>
    </form>
  ) : (
    <Link
      href="/login"
      className="inline-flex items-center justify-center whitespace-nowrap rounded-full bg-[var(--primary)] px-5 py-2 text-[18px] font-semibold leading-none text-[var(--on-primary)] shadow-[var(--shadow-card)] transition hover:bg-[var(--primary-hover)] hover:shadow-[var(--shadow-card-hover)]"
    >
      Войти
    </Link>
  );

  return (
    // Стеклянная шапка (.site-header, globals.css): плотность растёт с
    // прокруткой, data-scroll-dir для сворачивания — оба из GlassController.
    <header className="site-header sticky top-0 z-10">
      {/* header-logo/header-cta — сворачиваются при скролле вниз, см.
          globals.css (--header-collapse, пишет GlassController).
          ThemeToggle намеренно вне этой группы — остаётся на месте в
          правом углу, не участвует в сворачивании. */}
      <div className="header-row mx-auto flex max-w-5xl items-center gap-3 px-4 py-3 sm:py-4">
        <Link
          href="/"
          className="header-logo font-heading shrink-0 whitespace-nowrap text-[19px] font-bold tracking-wide text-[var(--accent-dark)] sm:text-[24px]"
        >
          Mirada Studio
        </Link>

        {/* Полное меню — только от sm и шире. На мобильном оно переносилось в
            несколько строк и съедало четверть экрана, поэтому ниже есть
            отдельная компактная версия. ml-auto держит nav (и всё, что
            после) прижатым к правому краю, пока лого видно; по мере того
            как лого сворачивается (--header-collapse), это же ml-auto
            естественно и плавно подтягивает nav влево вслед за
            освобождающимся местом — без отдельной анимации. */}
        <nav className="header-nav ml-auto hidden flex-wrap items-center gap-x-2 gap-y-2 sm:flex">
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
        <div className="header-right hidden items-center gap-3 sm:flex">
          <div className="header-cta overflow-hidden">{authSection}</div>
          <ThemeToggle />
        </div>

        {/* Компактная шапка на мобильном: лого + кнопка записи + тема + меню-иконка. */}
        <div className="ml-auto flex items-center gap-2 sm:hidden">
          <Link
            href="/schedule"
            className="inline-flex items-center justify-center whitespace-nowrap rounded-full bg-[var(--primary)] px-4 py-2 text-sm font-semibold leading-none text-[var(--on-primary)] shadow-[var(--shadow-card)] transition hover:bg-[var(--primary-hover)]"
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
