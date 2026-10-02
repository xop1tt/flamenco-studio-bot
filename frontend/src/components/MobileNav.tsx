"use client";

import { useState } from "react";
import { NavLink } from "./NavLink";

type NavItem = { href: string; label: string };

export function MobileNav({
  links,
  children,
}: {
  links: NavItem[];
  // Серверно отрендеренный блок входа/аккаунта — приходит как children,
  // чтобы логика auth/logoutAction оставалась на сервере, а этот компонент
  // отвечал только за открытие/закрытие меню.
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative sm:hidden">
      <button
        type="button"
        aria-label={open ? "Закрыть меню" : "Открыть меню"}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="flex h-10 w-10 items-center justify-center rounded-full border border-[var(--border-strong)] bg-[var(--surface)] text-lg transition hover:border-[var(--primary)]"
      >
        {open ? "✕" : "☰"}
      </button>
      {open && (
        <div className="glass-card absolute right-0 top-full mt-2 flex w-56 flex-col items-stretch gap-1 rounded-2xl p-3 shadow-[var(--shadow-card-hover)]">
          {links.map((link) => (
            <NavLink key={link.href} href={link.href}>
              {link.label}
            </NavLink>
          ))}
          {children}
        </div>
      )}
    </div>
  );
}
