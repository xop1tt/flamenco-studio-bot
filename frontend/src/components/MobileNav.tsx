"use client";

import { useEffect, useRef, useState } from "react";
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
  const rootRef = useRef<HTMLDivElement>(null);

  // Закрытие по клику снаружи и по Escape — ожидаемое поведение для
  // выпадающего меню, иначе единственный способ закрыть его — повторно
  // попасть по кнопке-гамбургеру.
  useEffect(() => {
    if (!open) return;

    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };

    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative sm:hidden">
      <button
        type="button"
        aria-label={open ? "Закрыть меню" : "Открыть меню"}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="glass-subtle glass-interactive flex h-10 w-10 items-center justify-center rounded-full text-lg"
      >
        {open ? "✕" : "☰"}
      </button>
      {open && (
        <div className="glass-dense absolute right-0 top-full mt-2 flex w-56 flex-col items-stretch gap-1 rounded-2xl p-3">
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
