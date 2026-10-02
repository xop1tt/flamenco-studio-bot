"use client";

import { useEffect, useState } from "react";

// Полупрозрачная шапка при прокрутке на 10% почти не видна и сливается с
// текстом страницы под ней — при скролле делаем фон заметнее (меньше
// прозрачности), чтобы навигация оставалась читаемой.
export function ScrollAwareHeader({ children }: { children: React.ReactNode }) {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={`sticky top-0 z-10 shadow-[var(--shadow-header)] backdrop-blur-md transition-colors ${
        scrolled ? "bg-[var(--surface)]/90" : "bg-[var(--surface)]/10"
      }`}
    >
      {children}
    </header>
  );
}
