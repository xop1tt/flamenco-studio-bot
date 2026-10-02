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
    <header className="border-b border-black/10 bg-[var(--background)]">
      <div className="mx-auto flex max-w-5xl flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
        <Link href="/" className="text-lg font-semibold tracking-wide">
          Flamenco Studio
        </Link>
        <nav className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="text-[var(--foreground)]/80 transition hover:text-[var(--accent)]"
            >
              {link.label}
            </Link>
          ))}
          {currentUser ? (
            <form action={logoutAction} className="flex items-center gap-3">
              <span className="text-[var(--foreground)]/70">
                {currentUser.display_name}
              </span>
              <button
                type="submit"
                className="text-[var(--foreground)]/80 underline-offset-2 transition hover:text-[var(--accent)] hover:underline"
              >
                Выйти
              </button>
            </form>
          ) : (
            <Link
              href="/login"
              className="rounded-md bg-[var(--accent)] px-3 py-1.5 font-medium text-white transition hover:opacity-90"
            >
              Войти
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
}
