import Link from "next/link";

const ACCOUNT_LINKS = [
  { href: "/account", label: "Профиль" },
  { href: "/account/bookings", label: "Мои занятия" },
  { href: "/account/payments", label: "Платежи" },
  { href: "/account/support", label: "Поддержка" },
];

export function AccountNav() {
  return (
    <nav className="flex flex-wrap gap-2">
      {ACCOUNT_LINKS.map((link) => (
        <Link
          key={link.href}
          href={link.href}
          className="rounded-full border border-[var(--border-strong)] bg-[var(--surface)] px-4 py-2 text-sm font-medium shadow-[var(--shadow-card)] transition hover:border-[var(--primary)] hover:text-[var(--primary)]"
        >
          {link.label}
        </Link>
      ))}
    </nav>
  );
}
