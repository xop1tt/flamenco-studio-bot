"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { NAV_ITEM_CLASS } from "@/lib/glass";

// Блик под курсором ведёт общий GlassController — своих обработчиков нет.

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
      className={`${NAV_ITEM_CLASS} ${
        isActive ? "text-[var(--primary)]" : "text-[var(--text-secondary)] hover:text-[var(--primary)]"
      }`}
    >
      {children}
    </Link>
  );
}
