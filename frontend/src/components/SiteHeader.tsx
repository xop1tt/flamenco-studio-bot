import Link from "next/link";
import { getCurrentUser } from "@/lib/auth";
import { logoutAction } from "@/lib/actions";

const NAV_LINKS = [
  { href: "/", label: "Главная" },
  { href: "/schedule", label: "Расписание" },
  { href: "/directions", label: "Направления" },
  { href: "/packages", label: "Абонементы" },
  { href: "/contact", label: "Контакты" },
];

export async function SiteHeader() {
  const currentUser = await getCurrentUser();

  return (
    <header className="border-b border-[var(--border)] bg-[var(--surface)]">
      <div className="mx-auto flex max-w-5xl flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
        <Link href="/" className="text-lg font-semibold tracking-wide">
          Flamenco Studio
        </Link>
        <nav className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="text-[var(--text-secondary)] transition hover:text-[var(--primary)]"
            >
              {link.label}
            </Link>
          ))}
          {currentUser ? (
            <form action={logoutAction} className="flex items-center gap-3">
              <Link
                href="/account"
                className="text-[var(--text-secondary)] transition hover:text-[var(--primary)]"
              >
                {currentUser.display_name}
              </Link>
              <button
                type="submit"
                className="text-[var(--text-secondary)] underline-offset-2 transition hover:text-[var(--primary)] hover:underline"
              >
                Выйти
              </button>
            </form>
          ) : (
            <Link
              href="/login"
              className="rounded-md bg-[var(--primary)] px-3 py-1.5 font-medium text-[var(--surface)] transition hover:bg-[var(--primary-hover)]"
            >
              Войти
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
}
