import Link from "next/link";
import { GLASS_BUTTON_CLASS } from "@/lib/glass";

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
          className={`${GLASS_BUTTON_CLASS} px-4 py-2 text-sm`}
        >
          {link.label}
        </Link>
      ))}
    </nav>
  );
}
