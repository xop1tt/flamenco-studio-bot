import { gsap, ScrollTrigger } from "@/lib/gsap";
import {
  buildChoreography,
  type Plan,
  type SceneRefs,
  type StageRefs,
} from "./choreography";

const clamp = (v: number, min: number, max: number) => Math.min(max, Math.max(min, v));
const opacityOf = (el: HTMLElement, fallback: number) =>
  el.style.opacity === "" ? fallback : parseFloat(el.style.opacity);

/**
 * Живой режим главной: sticky-"камера" высотой в экран внутри высокого
 * трека (.scenes), все сцены — слои внутри неё, и одна хореография
 * (choreography.ts) с временем = scroll progress.
 *
 * Скролл остаётся нативным — никакого перехвата wheel/touch. Движок только
 * читает scrollY и рисует кадр:
 *
 * - Сглаживание: видимый прогресс догоняет scrollY экспоненциальной
 *   пружиной (TAU ≈ 90 мс) — шаги колеса мыши (по ~100px) становятся
 *   плавным движением вместо "телепорта" объектов. Это всё ещё функция
 *   позиции: как только скролл остановился, кадр ровно f(scrollY), в обе
 *   стороны одинаково. На touch сглаживания нет — нативный скролл и так
 *   плавный, лаг ощущался бы как резина.
 * - Скорость прокрутки слегка раскачивает реквизит (кастаньеты крутятся,
 *   веер отстаёт) и затухает к нулю, когда скролл стоит.
 * - Переход с веером нельзя "проскочить насквозь": он занимает свой
 *   диапазон прокрутки, а следующая сцена существует только под ним. Если
 *   пользователь остановился, когда веер закрывает экран, переход мягко
 *   доводится в сторону последнего движения (нативный smooth scroll,
 *   любое касание/колесо его прерывает).
 *
 * Возвращает функцию очистки, полностью возвращающую DOM к статике.
 */
export function startSceneEngine(root: HTMLElement, nav: HTMLElement | null): () => void {
  const html = document.documentElement;
  const coarse = window.matchMedia("(pointer: coarse)").matches;
  const TAU = coarse ? 0 : 0.09;

  root.dataset.live = "";

  const sceneEls = Array.from(root.querySelectorAll<HTMLElement>("[data-scene]"));
  const q = (name: string) => root.querySelector<HTMLElement>(`[data-st="${name}"]`)!;
  const fanArt = root.querySelector<SVGSVGElement>(".stage-fan-art")!;
  const fanSwing = q("fan-swing");
  const castSpin = q("castanets-spin");
  const navButtons = nav ? Array.from(nav.querySelectorAll<HTMLButtonElement>("[data-scene-nav]")) : [];

  // Слои с размытием и цепочка их родительских слоёв: вложенный слой
  // наследует прозрачность панели, и размываться должен по ней.
  const blurLayers = sceneEls.flatMap((scene) =>
    Array.from(scene.querySelectorAll<HTMLElement>("[data-layer][data-blur]")).map((el) => {
      const chain: HTMLElement[] = [];
      for (let node: HTMLElement | null = el; node && node !== scene; node = node.parentElement) {
        if (node.hasAttribute("data-layer")) chain.push(node);
      }
      return { el, chain };
    }),
  );
  const lastBlur = new Map<HTMLElement, number>();

  let plan: Plan | null = null;
  let ctx: gsap.Context | null = null;
  let stage: StageRefs | null = null;
  let vhPx = 1;
  let trackTop = 0;
  let soft = false;

  let target = window.scrollY;
  let current = target;
  let velocity = 0;
  let active = -1;
  let lastDark = -1;

  // ---------- Построение ----------
  function measureScenes(): SceneRefs[] {
    return sceneEls.map((el) => {
      const scroller = el.querySelector<HTMLElement>("[data-scene-scroll]")!;
      const inner = scroller.firstElementChild as HTMLElement;
      return {
        el,
        scroller,
        layers: Array.from(el.querySelectorAll<HTMLElement>("[data-layer]")),
        hint: el.querySelector<HTMLElement>("[data-hint]"),
        overflow: Math.max(0, Math.ceil(inner.offsetHeight - scroller.clientHeight)),
      };
    });
  }

  function build() {
    // Высоту трека не сбрасываем: измерения от неё не зависят, а короткий
    // документ на мгновение обрезал бы scrollY.
    ctx?.revert();

    const viewport = root.querySelector<HTMLElement>("[data-viewport]")!;
    const vw = html.clientWidth;
    const vh = viewport.clientHeight;
    vhPx = vh;
    soft = !coarse && vw >= 768;

    const scenes = measureScenes();
    stage = {
      base: q("base"),
      floor: q("floor"),
      spot: q("spot"),
      beam: q("beam"),
      tone: q("tone"),
      glowA: q("glow-a"),
      glowB: q("glow-b"),
      lunares: q("lunares"),
      vignette: q("vignette"),
      fan: q("fan"),
      castanets: q("castanets"),
      // SVG-элемент: offsetWidth у него нет, а getBoundingClientRect
      // учитывал бы transform — берём CSS-ширину.
      fanWidth: parseFloat(getComputedStyle(fanArt).width) || 1000,
    };

    ctx = gsap.context(() => {
      plan = buildChoreography(scenes, stage!, { vw, vh, compact: vw < 768, soft });
    });

    root.style.height = `${Math.round(plan!.duration * vh + vh)}px`;
    trackTop = root.getBoundingClientRect().top + window.scrollY;
    lastDark = -1;
    active = -1;
    ScrollTrigger.refresh();
  }

  // ---------- Кадр ----------
  function setActive(index: number) {
    active = index;
    sceneEls.forEach((el, i) => el.toggleAttribute("data-active", i === index));
    navButtons.forEach((btn, i) => {
      if (i === index) btn.setAttribute("aria-current", "step");
      else btn.removeAttribute("aria-current");
    });
  }

  function render(y: number) {
    if (!plan || !stage) return;
    const t = clamp((y - trackTop) / vhPx, 0, plan.duration);
    plan.tl.time(t, true);

    // Глубина резкости: слой размывается, пока проявляется/исчезает.
    // Блюр — отдельно от таймлайна, чтобы в покое у слоёв не оставалось
    // filter: blur(0px) (лишний offscreen-проход на каждый текст).
    if (soft) {
      for (const { el, chain } of blurLayers) {
        let o = 1;
        for (const node of chain) o *= opacityOf(node, 1);
        const b = o < 0.02 ? 0 : Math.round((1 - o) * 70) / 10;
        if (lastBlur.get(el) !== b) {
          lastBlur.set(el, b);
          el.style.filter = b > 0 ? `blur(${b}px)` : "";
        }
      }
    }

    const index = plan.activeAt(t);
    if (index !== active) setActive(index);

    // Адаптивное стекло шапки: насколько тёмная сцена сейчас за ней.
    const dark = Math.round((1 - opacityOf(stage.tone, 0)) * 1000) / 1000;
    if (dark !== lastDark) {
      lastDark = dark;
      html.style.setProperty("--stage-dark", String(dark));
    }
  }

  function applyVelocity(v: number) {
    const spin = clamp(-v * 0.012, -16, 16);
    const sway = clamp(v * 0.003, -4, 4);
    castSpin.style.transform = Math.abs(spin) < 0.05 ? "" : `rotate(${spin.toFixed(2)}deg)`;
    fanSwing.style.transform = Math.abs(sway) < 0.02 ? "" : `rotate(${sway.toFixed(2)}deg)`;
  }

  // ---------- Цикл ----------
  let raf = 0;
  let lastTime = 0;
  function tick(now: number) {
    const dt = lastTime ? Math.min(0.064, (now - lastTime) / 1000) : 1 / 60;
    lastTime = now;
    const prev = current;
    current = TAU === 0 ? target : current + (target - current) * (1 - Math.exp(-dt / TAU));
    if (Math.abs(target - current) < 0.25) current = target;

    velocity += ((current - prev) / dt - velocity) * (1 - Math.exp(-dt / 0.12));
    render(current);
    applyVelocity(velocity);

    if (current !== target || Math.abs(velocity) > 4) {
      raf = requestAnimationFrame(tick);
    } else {
      raf = 0;
      lastTime = 0;
      velocity = 0;
      applyVelocity(0);
    }
  }
  const kick = () => {
    if (!raf) raf = requestAnimationFrame(tick);
  };

  // ---------- Довершение перехода с веером ----------
  let idleTimer = 0;
  let lastScrollY = window.scrollY;
  let direction = 1;
  let touching = false;

  function settleFan() {
    if (!plan || touching) return;
    const t = (window.scrollY - trackTop) / vhPx;
    const { start, end, snapFrom, snapTo } = plan.fan;
    if (t <= snapFrom || t >= snapTo) return;
    const dest = direction > 0 ? end : start;
    window.scrollTo({ top: trackTop + dest * vhPx, behavior: "smooth" });
  }

  // ---------- События ----------
  const onScroll = () => {
    const y = window.scrollY;
    if (y !== lastScrollY) direction = y > lastScrollY ? 1 : -1;
    lastScrollY = y;
    target = y;
    kick();
    window.clearTimeout(idleTimer);
    idleTimer = window.setTimeout(settleFan, 200);
  };
  const onTouchStart = () => {
    touching = true;
  };
  const onTouchEnd = () => {
    touching = false;
  };

  const scrollToScene = (index: number, behavior: ScrollBehavior) => {
    if (!plan) return;
    window.scrollTo({ top: trackTop + plan.settle[index] * vhPx, behavior });
  };

  // Клавиатура: невидимые сцены остаются в порядке табуляции (opacity, а
  // не visibility) — фокус, попавший в другую сцену, переносит к ней камеру.
  const onFocusIn = (event: FocusEvent) => {
    const scene = (event.target as Element | null)?.closest<HTMLElement>("[data-scene]");
    const index = scene ? sceneEls.indexOf(scene) : -1;
    if (index >= 0 && index !== active) scrollToScene(index, "instant");
  };

  const onNavClick = (event: MouseEvent) => {
    const btn = (event.target as Element | null)?.closest<HTMLElement>("[data-scene-nav]");
    if (btn) scrollToScene(Number(btn.dataset.sceneNav), "smooth");
  };

  // Якоря (/#directions): секция внутри sticky-камеры, браузер сам не
  // знает, на какой позиции скролла она видна.
  const onHash = () => {
    const id = decodeURIComponent(window.location.hash.slice(1));
    const index = sceneEls.findIndex((el) => el.id === id);
    if (index >= 0) scrollToScene(index, "instant");
  };

  function rebuild(preserve: boolean) {
    const loc = preserve && plan ? plan.locate((window.scrollY - trackTop) / vhPx) : null;
    build();
    if (loc && plan) {
      const y = Math.round(trackTop + (plan as Plan).timeAt(loc) * vhPx);
      window.scrollTo(0, y);
      target = current = y;
    } else {
      target = current = window.scrollY;
    }
    render(current);
  }

  // Мобильная адресная строка меняет высоту окна при каждом скролле —
  // такие изменения не перестраивают сцену (камера и так 100lvh).
  let lastW = window.innerWidth;
  let lastH = window.innerHeight;
  let resizeTimer = 0;
  const onResize = () => {
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(() => {
      const w = window.innerWidth;
      const h = window.innerHeight;
      if (w === lastW && (coarse ? Math.abs(h - lastH) < 160 : h === lastH)) return;
      lastW = w;
      lastH = h;
      rebuild(true);
    }, 120);
  };

  // Высота контента сцены (шрифты догрузились, данные обновились) —
  // меняет "прокрутку внутри сцены", пересчитываем.
  let observed = false;
  const resizeObserver = new ResizeObserver(() => {
    if (!observed) {
      observed = true;
      return;
    }
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(() => rebuild(true), 120);
  });

  // ---------- Старт ----------
  build();
  target = current = window.scrollY;
  render(current);
  applyVelocity(0);
  if (window.location.hash) onHash();

  sceneEls.forEach((el) => {
    const inner = el.querySelector("[data-scene-scroll]")?.firstElementChild;
    if (inner) resizeObserver.observe(inner);
  });
  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onResize);
  window.addEventListener("hashchange", onHash);
  window.addEventListener("touchstart", onTouchStart, { passive: true });
  window.addEventListener("touchend", onTouchEnd, { passive: true });
  window.addEventListener("touchcancel", onTouchEnd, { passive: true });
  root.addEventListener("focusin", onFocusIn);
  nav?.addEventListener("click", onNavClick);

  return () => {
    window.removeEventListener("scroll", onScroll);
    window.removeEventListener("resize", onResize);
    window.removeEventListener("hashchange", onHash);
    window.removeEventListener("touchstart", onTouchStart);
    window.removeEventListener("touchend", onTouchEnd);
    window.removeEventListener("touchcancel", onTouchEnd);
    root.removeEventListener("focusin", onFocusIn);
    nav?.removeEventListener("click", onNavClick);
    resizeObserver.disconnect();
    window.clearTimeout(idleTimer);
    window.clearTimeout(resizeTimer);
    if (raf) cancelAnimationFrame(raf);

    ctx?.revert();
    for (const { el } of blurLayers) el.style.filter = "";
    castSpin.style.transform = "";
    fanSwing.style.transform = "";
    sceneEls.forEach((el) => el.removeAttribute("data-active"));
    navButtons.forEach((btn) => btn.removeAttribute("aria-current"));
    root.style.height = "";
    delete root.dataset.live;
    html.style.removeProperty("--stage-dark");
    ScrollTrigger.refresh();
  };
}

/**
 * Статичный режим (prefers-reduced-motion): сцены — обычные блоки в потоке
 * страницы, без хореографии. Шапке всё равно нужно знать, тёмная ли сцена
 * под ней (адаптивное стекло в светлой теме).
 */
export function startStaticScenes(root: HTMLElement): () => void {
  const html = document.documentElement;
  const dark = Array.from(root.querySelectorAll<HTMLElement>(".scene--dark"));
  const update = () => {
    const probe = 40;
    const isDark = dark.some((el) => {
      const rect = el.getBoundingClientRect();
      return rect.top <= probe && rect.bottom > probe;
    });
    html.style.setProperty("--stage-dark", isDark ? "1" : "0");
  };
  update();
  window.addEventListener("scroll", update, { passive: true });
  window.addEventListener("resize", update);
  return () => {
    window.removeEventListener("scroll", update);
    window.removeEventListener("resize", update);
    html.style.removeProperty("--stage-dark");
  };
}
