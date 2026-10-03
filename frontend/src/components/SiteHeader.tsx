import Link from "next/link";
import { getCurrentUser } from "@/lib/auth";
import { logoutAction } from "@/lib/actions";
import { ScrollAwareHeader } from "./ScrollAwareHeader";
import { NavLink } from "./NavLink";
import { MobileNav } from "./MobileNav";
import { ThemeToggle } from "./ThemeToggle";

const NAV_LINKS = [
  { href: "/schedule", label: "Расписание" },
  { href: "/packages", label: "Абонементы" },
  { href: "/contact", label: "Контакты" },
];

const SECONDARY_ITEM_CLASS =
  "rounded-full border border-transparent px-3 py-1.5 text-[18px] font-semibold text-[var(--text-secondary)] transition hover:border-[var(--border-strong)] hover:bg-[var(--surface-secondary)] hover:text-[var(--primary)]";

export async function SiteHeader() {
  const currentUser = await getCurrentUser();

  const authSection = currentUser ? (
    <form action={logoutAction} className="flex flex-col items-start gap-1 sm:flex-row sm:items-center sm:gap-2">
      <NavLink href="/account">{currentUser.display_name}</NavLink>
      <button type="submit" className={SECONDARY_ITEM_CLASS}>
        Выйти
      </button>
    </form>
  ) : (
    <Link
      href="/login"
      className="block rounded-full bg-[var(--primary)] px-5 py-2 text-center text-[18px] font-semibold text-[var(--on-primary)] shadow-[var(--shadow-card)] transition hover:bg-[var(--primary-hover)] hover:shadow-[var(--shadow-card-hover)]"
    >
      Войти
    </Link>
  );

  return (
    <ScrollAwareHeader>
      <div className="mx-auto flex max-w-5xl items-center justify-between gap-3 px-4 py-3 sm:py-4">
        <Link href="/" className="font-heading shrink-0 whitespace-nowrap text-[18px] font-semibold tracking-wide text-[var(--accent-dark)] sm:text-[22px]">
          Mirada Studio
        </Link>

        {/* Полное меню — только от sm и шире. На мобильном оно переносилось в
            несколько строк и съедало четверть экрана, поэтому ниже есть
            отдельная компактная версия. */}
        <nav className="hidden flex-wrap items-center gap-x-2 gap-y-2 sm:flex">
          {NAV_LINKS.map((link) => (
            <NavLink key={link.href} href={link.href}>
              {link.label}
            </NavLink>
          ))}
          <div className="ml-1 flex items-center gap-2">
            {authSection}
            <ThemeToggle />
          </div>
        </nav>

        {/* Компактная шапка на мобильном: лого + кнопка записи + меню-иконка. */}
        <div className="flex items-center gap-2 sm:hidden">
          <Link
            href="/schedule"
            className="rounded-full bg-[var(--primary)] px-4 py-2 text-sm font-semibold text-[var(--on-primary)] shadow-[var(--shadow-card)] transition hover:bg-[var(--primary-hover)]"
          >
            Записаться
          </Link>
          <ThemeToggle />
          <MobileNav links={NAV_LINKS}>
            <div className="mt-2 border-t border-[var(--border)] pt-2">{authSection}</div>
          </MobileNav>
        </div>
      </div>
    </ScrollAwareHeader>
  );
}
