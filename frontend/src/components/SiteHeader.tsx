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
    <header className="sticky top-0 z-10 bg-[var(--surface)]/10 shadow-[var(--shadow-header)] backdrop-blur-md">
      <div className="mx-auto flex max-w-5xl flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
        <Link href="/" className="text-xl font-semibold tracking-wide text-[var(--accent-dark)]">
          Mirada Studio
        </Link>
        <nav className="flex flex-wrap items-center gap-x-6 gap-y-2 text-base">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="font-medium text-[var(--text-secondary)] transition hover:text-[var(--primary)]"
            >
              {link.label}
            </Link>
          ))}
          {currentUser ? (
            <form action={logoutAction} className="flex items-center gap-3">
              <Link
                href="/account"
                className="font-medium text-[var(--text-secondary)] transition hover:text-[var(--primary)]"
              >
                {currentUser.display_name}
              </Link>
              <button
                type="submit"
                className="font-medium text-[var(--text-secondary)] underline-offset-2 transition hover:text-[var(--primary)] hover:underline"
              >
                Выйти
              </button>
            </form>
          ) : (
            <Link
              href="/login"
              className="rounded-full bg-[var(--primary)] px-5 py-2 font-medium text-[var(--surface)] shadow-[var(--shadow-card)] transition hover:bg-[var(--primary-hover)] hover:shadow-[var(--shadow-card-hover)]"
            >
              Войти
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
}
