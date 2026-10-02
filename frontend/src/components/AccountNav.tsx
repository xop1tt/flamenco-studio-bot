import Link from "next/link";

const ACCOUNT_LINKS = [
  { href: "/account", label: "Профиль" },
  { href: "/account/bookings", label: "Мои занятия" },
  { href: "/account/support", label: "Поддержка" },
];

export function AccountNav() {
  return (
    <nav className="flex flex-wrap gap-2">
      {ACCOUNT_LINKS.map((link) => (
        <Link
          key={link.href}
          href={link.href}
          className="rounded-full border border-black/15 px-4 py-1.5 text-sm font-medium transition hover:border-[var(--accent)] hover:text-[var(--accent)]"
        >
          {link.label}
        </Link>
      ))}
    </nav>
  );
}
