"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { gsap, ScrollTrigger } from "@/lib/gsap";

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
 * Подвижных объектов на сцене больше нет (веер убран по запросу) — фон
 * состоит только из статичных слоёв (.stage-base, .stage-spot, .stage-tone)
 * с плавным сдвигом софита/тона и затемнением по ходу скролла; весь
 * "сюжет" сцены — это появление контента (reveal) поверх неё.
 *
 *   0 hero        тёмная сцена: софит в одном положении
 *   0→1           софит/тон смещаются, сцена растворяется в тоне About
 *   1 about       светлая тема, контент панели «Почему мы?»
 *   1→3           тон продолжает мягкий сдвиг через Directions к Schedule
 *   3 schedule    тон справа
 *   3→4           сцена снова темнеет к CTA
 *   4 cta         тёмная сцена — "после танца"
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
      const spot = q("spot");
      const tone = q("tone");
      const toneGlow = q("tone-glow");

      const tl = gsap.timeline({ paused: true, defaults: { ease: "power1.inOut", duration: 1 } });
      // Появление контента — fromTo (а не from): таймлайн пересобирается на
      // ресайзе, и from() записал бы скрытое состояние как конечное.
      const reveal = (el: HTMLElement | null, from: gsap.TweenVars, position: number, duration = 0.3) => {
        if (!el) return;
        tl.fromTo(el, { autoAlpha: 0, ...from }, { autoAlpha: 1, x: 0, y: 0, scale: 1, rotateX: 0, duration, ease: "power2.out" }, position);
      };

      // ---------- Сцена 1 → 2: Hero раскручивается в About ----------
      tl.to(spot, { "--spot-x": "38%", "--spot-y": "42%", "--spot-r": "78%", "--spot-color": "rgba(214, 112, 52, 0.55)", duration: 0.6 }, 0)
        .to(spot, { "--spot-x": "50%", "--spot-y": "18%", "--spot-color": "rgba(120, 20, 36, 0.5)", duration: 0.4 }, 0.6)
        .to(tone, { opacity: 1, duration: 0.4 }, 0.6)
        .to(toneGlow, { "--glow-x": "15%", "--glow-y": "62%", "--tone-hue": "-8deg", duration: 1 }, 1)
        .to(toneGlow, { "--glow-x": "85%", "--glow-y": "40%", "--tone-hue": "6deg", duration: 1 }, 2);

      const heroText = sb("hero-text");
      if (heroText) tl.to(heroText, { autoAlpha: 0, y: -50, duration: 0.3, ease: "power1.in" }, 0);

      // Панель «Почему мы?» в обычном потоке страницы (не анимируется
      // целиком) въезжает в кадр заметно раньше, чем раньше стартовал
      // текст внутри неё (0.72) — отсюда была пустая плитка на пол-экрана.
      // Сдвинуто раньше, чтобы текст появлялся почти сразу, как заголовок
      // панели показывается на экране.
      reveal(sb("about-heading"), { y: 40 }, 0.42);
      reveal(sb("about-intro"), { y: 30 }, 0.5);
      root.querySelectorAll<HTMLElement>('[data-sb="about-tile"]').forEach((tile, i) => {
        reveal(tile, { y: 50, scale: 0.88 }, 0.58 + i * 0.05, 0.25);
      });

      // ---------- Сцена 2 → 3: Directions ----------
      reveal(sb("directions-heading"), { y: 40 }, 1.55);
      reveal(sb("directions-stage"), { y: 60, scale: 0.92, rotateX: 8 }, 1.6, 0.4);

      // ---------- Сцена 3 → 4: Schedule ----------
      reveal(sb("schedule-heading"), { y: 40 }, 2.55);
      reveal(sb("schedule-stage"), { y: 70 }, 2.6, 0.4);

      // ---------- Сцена 4 → 5: снова тёмная сцена — "после танца" ----------
      tl.to(tone, { opacity: 0, duration: 0.5 }, 3.3)
        .to(spot, { "--spot-x": "60%", "--spot-y": "55%", "--spot-r": "60%", "--spot-color": "rgba(190, 28, 52, 0.5)", duration: 0.6 }, 3.2);
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
