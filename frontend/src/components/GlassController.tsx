"use client";

import { useEffect } from "react";
import { ScrollTrigger } from "@/lib/gsap";

const HEADER_DENSITY_DISTANCE = 240;
// --header-collapse = clamp(scrollY / HEADER_COLLAPSE_RANGE, 0, 1) — ЧИСТАЯ
// функция абсолютной позиции скролла, как и --glass-header-density выше.
// Важно: НЕ накопленная дельта/путь. Первая версия этого контроллера
// считала collapse как клампованную сумму дельт (чтобы сымитировать
// классический "спрятать при скролле вниз, показать при скролле вверх
// в любом месте страницы" хедер) — но это ломает главное требование:
// одна и та же scroll-позиция должна всегда давать одно и то же
// состояние, независимо от того, как пользователь до неё докрутил.
// Проверено: с накоплением y=45 после "докрутили до 200 и обратно" давал
// collapse=0, а y=45 "докрутили прямо от 0" — collapse=0.5. Чистая
// функция позиции устраняет это: на длинной странице шапка остаётся
// свёрнутой до тех пор, пока пользователь не вернётся к самому верху —
// это единственное отличие от направленного поведения, и оно прямое
// следствие требования детерминированности. См. .header-logo/.header-cta
// в globals.css.
const HEADER_COLLAPSE_RANGE = 140;

const clamp01 = (n: number) => Math.min(1, Math.max(0, n));
const SPECULAR_SELECTOR = ".glass-interactive, .glass-specular";

/**
 * Единственный источник "живых" параметров glass-материала и шапки,
 * монтируется один раз в layout:
 *
 * 1. Scroll — тот же GSAP ScrollTrigger, что и у scroll-сцен главной (не
 *    второй scroll-листенер): пишет на <html>
 *      --glass-header-density  (0..1)
 *      --header-collapse       (0..1)
 *    обе — чистые функции абсолютной scroll-позиции (f(scrollY)),
 *    обновляются на каждый тик скролла — никакого play()/reverse() и
 *    никакого состояния, зависящего от истории жеста.
 * 2. Pointer — один pointermove на document + один rAF: двигает --mx/--my
 *    только у того glass-элемента, что сейчас под курсором. Только мышь и
 *    только без prefers-reduced-motion; на touch блика нет вовсе (CSS).
 *
 * Ничего не рендерит.
 */
export function GlassController() {
  useEffect(() => {
    const root = document.documentElement;

    const applyScroll = (y: number) => {
      const density = clamp01(y / HEADER_DENSITY_DISTANCE);
      root.style.setProperty("--glass-header-density", density.toFixed(3));

      const collapse = clamp01(y / HEADER_COLLAPSE_RANGE);
      root.style.setProperty("--header-collapse", collapse.toFixed(4));
      // Чисто для a11y/кликабельности в полностью свёрнутом состоянии
      // (клавиатурный фокус на невидимом элементе) — само визуальное
      // сворачивание уже целиком отрисовано через --header-collapse выше,
      // этот атрибут ничего не анимирует.
      root.dataset.headerCollapsed = collapse > 0.98 ? "true" : "false";
    };

    applyScroll(window.scrollY);

    const trigger = ScrollTrigger.create({
      start: 0,
      end: "max",
      onUpdate: (self) => applyScroll(self.scroll()),
      onRefresh: (self) => applyScroll(self.scroll()),
    });

    return () => {
      trigger.kill();
      root.style.removeProperty("--glass-header-density");
      root.style.removeProperty("--header-collapse");
      delete root.dataset.headerCollapsed;
    };
  }, []);

  useEffect(() => {
    const canHover = window.matchMedia("(hover: hover) and (pointer: fine)");
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (!canHover.matches || reducedMotion.matches) return;

    let frame = 0;
    let lastEvent: PointerEvent | null = null;

    const update = () => {
      frame = 0;
      const event = lastEvent;
      if (!event || !(event.target instanceof Element)) return;
      const el = event.target.closest<HTMLElement>(SPECULAR_SELECTOR);
      if (!el) return;
      const rect = el.getBoundingClientRect();
      el.style.setProperty("--mx", `${((event.clientX - rect.left) / rect.width) * 100}%`);
      el.style.setProperty("--my", `${((event.clientY - rect.top) / rect.height) * 100}%`);
    };

    const onPointerMove = (event: PointerEvent) => {
      if (event.pointerType !== "mouse") return;
      lastEvent = event;
      if (!frame) frame = requestAnimationFrame(update);
    };

    document.addEventListener("pointermove", onPointerMove, { passive: true });
    return () => {
      document.removeEventListener("pointermove", onPointerMove);
      if (frame) cancelAnimationFrame(frame);
    };
  }, []);

  return null;
}
