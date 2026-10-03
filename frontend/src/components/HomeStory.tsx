"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { gsap, ScrollTrigger } from "@/lib/gsap";
import { PETALS } from "./home/HomeStage";

const SCENES = ["hero", "about", "directions", "schedule", "cta"] as const;

/**
 * Хореография главной: ОДИН таймлайн (время 0…4, метка на сцену) и ОДНА
 * функция scrollY → время, применяемая НАПРЯМУЮ (tl.time(...) в каждом
 * onUpdate, без промежуточного tween/easing до цели) — состояние сцены
 * буквально равно f(scrollProgress) в любой момент, а не "подъезжает" к
 * нему с задержкой. Направление жеста нигде не участвует: одна и та же
 * scroll-позиция — всегда одно и то же визуальное состояние, обратный
 * скролл проходит ту же траекторию в обратную сторону без play()/reverse().
 *
 *   0 hero        тёмная сцена: дымка, софит, веер в стороне, «FLAMENCO»
 *   0→1           фон приближается и теплеет, тип уезжает, веер выходит
 *                 вперёд и "раскрывается" (scaleX), кастаньеты пересекают
 *                 кадр, лепестки разлетаются от веера, сцена растворяется
 *                 в тоне следующей
 *   1 about       раскрытый веер — акцентом слева от панели «Почему мы?»
 *   2 directions  веер по центру-слева, кастаньеты справа у заголовка
 *   3 schedule    веер справа, падает роза
 *   4 cta         фон снова тёмная сцена; веер складывается и уходит вниз,
 *                 роза остаётся лежать рядом — сцена "после танца"
 *
 * Якоря сцен меряются по DOM (центр секции в центре экрана), между
 * якорями — линейная интерполяция. ВАЖНО: высота самих секций в
 * нормальном, некомпенсированном scroll-потоке (page.tsx) — анимация не
 * растягивает секции искусственно, лишние 60dvh есть только у hero (один
 * действительно насыщенный переход, см. [data-story-live] [data-scene=hero]
 * в globals.css), у остальных секций — обычные отступы.
 */
export function HomeStory({ children }: { children: ReactNode }) {
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const html = document.documentElement;
    const stage = root.querySelector<HTMLElement>('[data-st="stage"]');
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // Без хореографии сцена — просто статичный hero-кадр (CSS), который
    // уезжает вместе со страницей. Шапке всё равно нужно знать, что за
    // ней тёмная сцена (адаптивное стекло) — непрерывно по скроллу hero.
    if (reduced || !stage) {
      const hero = root.querySelector('[data-scene="hero"]');
      const setDark = (p: number) => html.style.setProperty("--stage-dark", (1 - p).toFixed(3));
      setDark(0);
      const st = ScrollTrigger.create({
        trigger: hero,
        start: "top top",
        end: "bottom top",
        onUpdate: (self) => setDark(self.progress),
        onRefresh: (self) => setDark(self.progress),
      });
      return () => {
        st.kill();
        html.style.removeProperty("--stage-dark");
      };
    }

    root.dataset.storyLive = "1";

    const q = (name: string) => root.querySelector<HTMLElement>(`[data-st="${name}"]`)!;
    const sb = (name: string) => root.querySelector<HTMLElement>(`[data-sb="${name}"]`);
    const vw = (n: number) => (n * window.innerWidth) / 100;
    const vh = (n: number) => (n * window.innerHeight) / 100;

    // Позиция элемента без учёта transform — относительно (fixed) сцены.
    const basePoint = (el: HTMLElement) => {
      let x = 0;
      let y = 0;
      let node: HTMLElement | null = el;
      while (node && node !== stage) {
        x += node.offsetLeft;
        y += node.offsetTop;
        node = node.offsetParent as HTMLElement | null;
      }
      return { x, y };
    };
    // Якорь объекта → точка экрана (X vw, Y vh).
    const at = (el: HTMLElement, X: number, Y: number) => ({
      x: () => vw(X) - basePoint(el).x,
      y: () => vh(Y) - basePoint(el).y,
    });

    let anchors: number[] = [];
    const measure = () => {
      const max = ScrollTrigger.maxScroll(window);
      anchors = SCENES.map((scene, i) => {
        if (i === 0) return 0;
        if (i === SCENES.length - 1) return max;
        const el = root.querySelector(`[data-scene="${scene}"]`)!;
        const rect = el.getBoundingClientRect();
        return rect.top + window.scrollY + rect.height / 2 - window.innerHeight / 2;
      });
      for (let i = 1; i < anchors.length; i++) {
        anchors[i] = Math.min(max, Math.max(anchors[i], anchors[i - 1] + 1));
      }
    };
    const timeAt = (y: number) => {
      if (y <= anchors[0]) return 0;
      for (let i = 0; i < anchors.length - 1; i++) {
        if (y < anchors[i + 1]) return i + (y - anchors[i]) / (anchors[i + 1] - anchors[i]);
      }
      return SCENES.length - 1;
    };

    const ctx = gsap.context(() => {
      const haze = q("haze");
      const spot = q("spot");
      const tone = q("tone");
      const toneGlow = q("tone-glow");
      const type = q("type");
      const fan = q("fan");
      const castanets = q("castanets");
      const rose = q("rose");
      const petals = Array.from(root.querySelectorAll<HTMLElement>('[data-st="petal"]'));

      const tl = gsap.timeline({ paused: true, defaults: { ease: "power1.inOut", duration: 1 } });
      // Появление контента — fromTo (а не from): таймлайн пересобирается на
      // ресайзе, и from() записал бы скрытое состояние как конечное.
      const reveal = (el: HTMLElement | null, from: gsap.TweenVars, position: number, duration = 0.3) => {
        if (!el) return;
        tl.fromTo(el, { autoAlpha: 0, ...from }, { autoAlpha: 1, x: 0, y: 0, scale: 1, rotateX: 0, duration, ease: "power2.out" }, position);
      };

      // ---------- Сцена 1 → 2: Hero раскручивается в About ----------
      tl.to(haze, { scale: 1.35, xPercent: -6, rotation: 4, duration: 1 }, 0)
        .to(haze, { opacity: 0.85, duration: 0.45 }, 0)
        .to(haze, { opacity: 0.25, duration: 0.5 }, 0.5)
        .to(spot, { "--spot-x": "38%", "--spot-y": "42%", "--spot-r": "78%", "--spot-color": "rgba(214, 112, 52, 0.55)", duration: 0.6 }, 0)
        .to(spot, { "--spot-x": "50%", "--spot-y": "18%", "--spot-color": "rgba(120, 20, 36, 0.5)", duration: 0.4 }, 0.6)
        .to(tone, { opacity: 1, duration: 0.4 }, 0.6)
        .to(type, { xPercent: -28, scale: 1.25, opacity: 0, duration: 0.9 }, 0);

      const heroText = sb("hero-text");
      if (heroText) tl.to(heroText, { autoAlpha: 0, y: -50, duration: 0.3, ease: "power1.in" }, 0);

      // Веер: выходит из статичного "сложенного" ракурса (scaleX сжат,
      // см. исходный transform в globals.css) вперёд и в центр, scaleX
      // распускается до 1 — читается как раскрытие, без покадровой
      // анимации пластин (сам ассет — фотография, не вектор).
      tl.to(fan, { ...at(fan, 50, 36), rotation: -6, scale: 1.05, duration: 0.55, ease: "power2.out" }, 0.12)
        .to(fan, { ...at(fan, 32, 44), rotation: 4, scale: 0.9, duration: 0.35 }, 0.68)
        .to(fan, { opacity: 0.65, duration: 0.3 }, 0.72);

      // Кастаньеты пересекают передний план слева направо по нижней трети.
      tl.to(castanets, { ...at(castanets, 16, 62), rotation: 8, scale: 1.15, duration: 0.45, ease: "power2.out" }, 0.1)
        .to(castanets, { ...at(castanets, 112, 86), rotation: 120, scale: 0.8, duration: 0.45, ease: "power2.in" }, 0.55);

      petals.forEach((petal, i) => {
        const p = PETALS[i];
        const start = 0.2 + i * 0.05;
        tl.to(petal, { opacity: 1, scale: 1, duration: 0.15 }, start)
          .to(petal, { ...at(petal, p.to[0], p.to[1]), rotation: p.spin, filter: `blur(${p.blur}px)`, duration: 0.85, ease: "power1.out" }, start)
          .to(petal, { opacity: 0, duration: 0.25 }, start + 0.65);
      });

      reveal(sb("about-heading"), { y: 40 }, 0.72);
      reveal(sb("about-intro"), { y: 30 }, 0.78);
      root.querySelectorAll<HTMLElement>('[data-sb="about-tile"]').forEach((tile, i) => {
        reveal(tile, { y: 50, scale: 0.88 }, 0.8 + i * 0.05, 0.2);
      });

      // ---------- Сцена 2 → 3: Directions ----------
      tl.to(fan, { ...at(fan, 15, 60), rotation: -14, scale: 0.78, opacity: 0.8, duration: 1 }, 1)
        .to(toneGlow, { "--glow-x": "15%", "--glow-y": "62%", "--tone-hue": "-8deg", duration: 1 }, 1)
        .to(castanets, { ...at(castanets, 84, 26), rotation: -18, scale: 0.6, duration: 0.5, ease: "power2.out" }, 1.45)
        .to(castanets, { ...at(castanets, 114, 72), rotation: -80, scale: 0.5, duration: 0.5, ease: "power2.in" }, 2.1);
      reveal(sb("directions-heading"), { y: 40 }, 1.55);
      reveal(sb("directions-stage"), { y: 60, scale: 0.92, rotateX: 8 }, 1.6, 0.4);

      // ---------- Сцена 3 → 4: Schedule ----------
      tl.to(fan, { ...at(fan, 85, 42), rotation: 16, scale: 0.6, opacity: 0.65, duration: 1 }, 2)
        .to(toneGlow, { "--glow-x": "85%", "--glow-y": "40%", "--tone-hue": "6deg", duration: 1 }, 2)
        .to(rose, { ...at(rose, 10, 30), rotation: 14, scale: 1, duration: 0.7, ease: "power2.out" }, 2.25);
      reveal(sb("schedule-heading"), { y: 40 }, 2.55);
      reveal(sb("schedule-stage"), { y: 70 }, 2.6, 0.4);

      // ---------- Сцена 4 → 5: снова тёмная сцена — "после танца":
      // веер складывается (scaleX сжимается) и опускается, роза ложится
      // рядом. Больше некуда "вручать" реквизит (второй танцовщицы нет),
      // поэтому сцена — не передача объекта, а естественное завершение. ----------
      tl.to(tone, { opacity: 0, duration: 0.5 }, 3.3)
        .to(spot, { "--spot-x": "60%", "--spot-y": "55%", "--spot-r": "60%", "--spot-color": "rgba(190, 28, 52, 0.5)", duration: 0.6 }, 3.2)
        .to(haze, { opacity: 0.4, scale: 1.1, xPercent: 3, rotation: -2, duration: 0.8 }, 3.2)
        // scaleX/scaleY явно (не шорткат scale) — ниже отдельный tween
        // продолжает анимировать именно scaleX ("складывание"), и шорткат
        // scale на пересекающемся отрезке времени переписывал бы его же
        // scaleX своим собственным выводом при каждом рендере таймлайна.
        .to(fan, { ...at(fan, 52, 78), rotation: -4, scaleX: 0.7, scaleY: 0.7, duration: 0.6, ease: "power2.out" }, 3.3)
        .to(fan, { scaleX: 0.3, duration: 0.5, ease: "power2.in" }, 3.5)
        .to(fan, { opacity: 0.85, duration: 0.3 }, 3.3)
        .to(rose, { ...at(rose, 62, 82), rotation: -20, scale: 0.55, duration: 0.6, ease: "power2.out" }, 3.35);
      reveal(sb("cta-heading"), { y: 30 }, 3.5);
      reveal(sb("cta-button"), { scale: 0.7 }, 3.58);
      reveal(sb("cta-contacts"), { y: 50 }, 3.62);
      tl.set({}, {}, SCENES.length - 1);

      // Адаптивное стекло шапки: насколько тёмная сцена сейчас за ней.
      const stageDark = (t: number) =>
        t < 0.6 ? 1 : t < 1 ? 1 - (t - 0.6) / 0.4 : t < 3.3 ? 0 : t < 3.8 ? (t - 3.3) / 0.5 : 1;
      const applyTime = (t: number) => {
        tl.time(t);
        html.style.setProperty("--stage-dark", stageDark(t).toFixed(3));
      };

      ScrollTrigger.create({
        start: 0,
        end: "max",
        // Прямое присваивание времени таймлайна на каждый тик скролла —
        // НЕ gsap.to(tl, {time: ...}) с собственной длительностью/easing.
        // Любой "догоняющий" tween создавал бы лаг между положением
        // скролла и видимым состоянием — ровно то, чего просит избежать
        // техзадание (состояние должно быть f(scrollProgress) синхронно,
        // а не подъезжать к цели по своей отдельной временной шкале).
        onUpdate: (self) => applyTime(timeAt(self.scroll())),
        onRefresh: (self) => {
          measure();
          tl.time(0).invalidate();
          applyTime(timeAt(self.scroll()));
        },
      });
    }, root);

    ScrollTrigger.refresh();

    return () => {
      ctx.revert();
      delete root.dataset.storyLive;
      html.style.removeProperty("--stage-dark");
    };
  }, []);

  return <div ref={rootRef}>{children}</div>;
}
