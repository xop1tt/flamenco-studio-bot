"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const BASE =
  "rounded-full border px-3 py-1.5 text-[18px] font-semibold transition hover:border-[var(--border-strong)] hover:bg-[var(--surface-secondary)] hover:text-[var(--primary)]";

export function NavLink({
  href,
  children,
}: {
  href: string;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const isActive = pathname === href;

  return (
    <Link
      href={href}
      aria-current={isActive ? "page" : undefined}
      className={`${BASE} ${
        isActive
          ? "border-[var(--border-strong)] bg-[var(--surface-secondary)] text-[var(--primary)]"
          : "border-transparent text-[var(--text-secondary)]"
      }`}
    >
      {children}
    </Link>
  );
}
