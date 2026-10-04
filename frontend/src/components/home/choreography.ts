import { gsap } from "@/lib/gsap";
import { FAN_INNER_RATIO, FAN_RADIUS_RATIO } from "./fanGeometry";

// Хореография главной: ОДИН GSAP-таймлайн на все сцены. Время таймлайна
// измеряется в "экранах прокрутки" (1 = одна высота viewport), поэтому
// движок просто делает tl.time(scrollY / vh) — состояние сцены всегда
// f(scroll progress), одинаковое при прокрутке вниз и вверх.
//
// Таймлайн — последовательность сегментов:
//
//   hold(hero) → move(hero→directions, ВЕЕР) → hold(directions) →
//   move(→about) → hold(about) → move(→schedule) → hold(schedule) →
//   move(→contacts) → hold(contacts)
//
// move — "камера" переходит в следующую сцену (контент уходит/входит с
// параллаксом по глубине data-depth, фон и реквизит двигаются вместе с
// ним). hold — сцена стоит: лёгкий дрейф, а если контент выше экрана
// (мобильные), он прокручивается внутри сцены 1:1 со скроллом.

export type SceneRefs = {
  el: HTMLElement;
  /** Обёртка, которую двигаем по Y в hold (дрейф + прокрутка контента). */
  scroller: HTMLElement;
  /** Слои контента ([data-layer]) в порядке DOM. */
  layers: HTMLElement[];
  hint: HTMLElement | null;
  /** Насколько контент выше доступной высоты сцены, px. */
  overflow: number;
};

export type StageRefs = {
  base: HTMLElement;
  floor: HTMLElement;
  spot: HTMLElement;
  beam: HTMLElement;
  tone: HTMLElement;
  glowA: HTMLElement;
  glowB: HTMLElement;
  lunares: HTMLElement;
  vignette: HTMLElement;
  fan: HTMLElement;
  castanets: HTMLElement;
  /** Ширина SVG веера при scale 1, px. */
  fanWidth: number;
};

export type Metrics = {
  vw: number;
  vh: number;
  /** Узкий экран: короче сегменты, меньше амплитуды, своя раскладка реквизита. */
  compact: boolean;
  /** Можно ли размывать (blur) — только десктоп, на мобильных дорого. */
  soft: boolean;
};

export type Segment = { kind: "hold" | "move"; scene: number; start: number; dur: number };

export type Plan = {
  tl: gsap.core.Timeline;
  duration: number;
  segments: Segment[];
  /** Время, к которому сцена i полностью "встала" (начало её hold). */
  settle: number[];
  /** Активная сцена (принимает клики) по времени таймлайна. */
  activeAt: (t: number) => number;
  /** Переход с веером: границы и окно, где веер закрывает экран. */
  fan: { start: number; end: number; snapFrom: number; snapTo: number };
  locate: (t: number) => { seg: number; frac: number };
  timeAt: (loc: { seg: number; frac: number }) => number;
};

const depthOf = (el: HTMLElement) => Number(el.dataset.depth ?? "1") || 1;
// Вложенный слой (текст внутри стеклянной панели) двигается с собственным
// параллаксом, но прозрачность наследует от родителя: иначе пустая панель
// появлялась бы раньше своего текста.
const isNested = (el: HTMLElement) => el.parentElement?.closest("[data-layer]") != null;

/**
 * Радиус листа, при котором веер с шарниром в (px, vh + drop·R) закрывает
 * весь экран тканью: оба верхних угла — внутри внешнего радиуса. drop
 * больше доли внутреннего радиуса, поэтому зона пластин с просветами
 * остаётся ниже нижнего края экрана.
 */
function coverRadius(vw: number, vh: number, px: number, drop: number) {
  const dx = Math.max(px, vw - px);
  const a = 1 - drop * drop;
  const b = -2 * drop * vh;
  const c = -(dx * dx + vh * vh);
  return (-b + Math.sqrt(b * b - 4 * a * c)) / (2 * a);
}

export function buildChoreography(scenes: SceneRefs[], st: StageRefs, m: Metrics): Plan {
  const { vw, vh, compact } = m;
  const L = compact
    ? { fan: 2.1, move: 0.9, hold: 0.4, last: 0.3 }
    : { fan: 2.5, move: 1.05, hold: 0.5, last: 0.35 };
  const lastIndex = scenes.length - 1;

  // ---------- Сегменты ----------
  const segments: Segment[] = [];
  const settle: number[] = [];
  let cursor = 0;
  scenes.forEach((scene, i) => {
    if (i > 0) {
      const dur = i === 1 ? L.fan : L.move;
      segments.push({ kind: "move", scene: i, start: cursor, dur });
      cursor += dur;
    }
    settle.push(cursor);
    const base = i === 0 ? 0 : i === lastIndex ? L.last : L.hold;
    const dur = base + scene.overflow / vh;
    segments.push({ kind: "hold", scene: i, start: cursor, dur });
    cursor += dur;
  });
  const duration = cursor;
  const moves = segments.filter((s) => s.kind === "move");
  // Клики переходят к следующей сцене в середине перехода; в переходе с
  // веером — позже, когда веер уже накрыл экран и новая сцена под ним.
  const boundaries = moves.map((s, k) => s.start + s.dur * (k === 0 ? 0.7 : 0.5));

  const tl = gsap.timeline({ paused: true, defaults: { ease: "none" } });

  // ---------- Исходный кадр (время 0) ----------
  const D = vw * (compact ? 0.22 : 0.28); // шаг "камеры" между сценами
  const drift = vh * 0.02;

  scenes.forEach((scene, i) => {
    gsap.set(scene.scroller, { y: i === 0 ? 0 : drift });
    if (i === 0) return;
    scene.layers.forEach((el) => {
      const z = depthOf(el);
      const from =
        i === 1
          ? { x: vw * 0.08 * z, scale: 1.05 }
          : i === lastIndex
            ? { y: vh * 0.08 * z }
            : { x: D * z, scale: 1.03 };
      gsap.set(el, isNested(el) ? from : { opacity: 0, ...from });
    });
  });

  gsap.set(st.tone, { opacity: 0 });
  gsap.set(st.vignette, { opacity: 1 });
  gsap.set([st.base, st.floor], { scale: 1, transformOrigin: "60% 55%" });
  gsap.set(st.spot, { x: 0, scale: 1 });
  gsap.set(st.beam, { x: 0, rotation: 0 });
  gsap.set(st.glowA, { x: vw * 0.12, y: 0 });
  gsap.set(st.glowB, { x: vw * 0.08, y: 0 });
  gsap.set(st.lunares, { x: vw * 0.06 });

  // Реквизит. Размер веера задаём радиусом листа в px → scale.
  const fanUnit = st.fanWidth * FAN_RADIUS_RATIO;
  const sc = (radius: number) => radius / fanUnit;
  // Портретный экран шире телефона (планшет): текст hero занимает всю
  // ширину, поэтому реквизит — под текстом, как на телефоне, а не справа.
  const portrait = !compact && vh > vw * 1.1;
  const low = compact || portrait;
  const R0 = compact
    ? Math.min(vw * 0.44, vh * 0.25)
    : portrait
      ? Math.min(vw * 0.3, vh * 0.24)
      : Math.min(vh * 0.36, vw * 0.23);
  const C = compact ? 0.6 : portrait ? 0.8 : Math.min(1, Math.max(0.7, vh / 900));
  const fanHome = compact
    ? { x: vw * 0.74, y: vh * 0.95, rotation: -12 }
    : portrait
      ? { x: vw * 0.68, y: vh * 0.9, rotation: -10 }
      : { x: vw * 0.74, y: vh * 0.66, rotation: -10 };
  const castHome = low
    ? { x: vw * 0.24, y: vh * 0.92, rotation: -10 }
    : { x: vw * 0.87, y: vh * 0.87, rotation: 16 };

  gsap.set(st.fan, { ...fanHome, scale: sc(R0), opacity: 0.86, zIndex: 1 });
  gsap.set(st.castanets, {
    ...castHome,
    scale: C,
    opacity: 1,
    // Кастаньеты на переднем плане, ближе фокуса — слегка размыты.
    filter: m.soft ? "blur(2.5px)" : "none",
  });

  // ---------- Переход 1: Hero → Направления, веер ----------
  const T0 = moves[0];
  const at = (p: number) => T0.start + p * T0.dur;
  const len = (p: number) => p * T0.dur;

  const drop = FAN_INNER_RATIO + 0.05;
  const Px = vw * 0.55;
  const Rc = coverRadius(vw, vh, Px, drop) * 1.06;
  const Py = vh + drop * Rc;

  const hero = scenes[0];
  // Текст hero "сдувает" влево приближающимся веером: уходит раньше, чем
  // веер выйдет вперёд (0.445), — смена z-index в этот момент не видна.
  hero.layers.forEach((el, k) => {
    const z = depthOf(el);
    tl.to(el, { x: -vw * 0.1 * z, y: -vh * 0.025 * z, duration: len(0.42), ease: "power1.in" }, at(0));
    if (!isNested(el)) tl.to(el, { opacity: 0, duration: len(0.18), ease: "power1.in" }, at(0.17 + k * 0.025));
  });
  if (hero.hint) tl.to(hero.hint, { opacity: 0, y: 14, duration: len(0.06) }, at(0));

  // Веер:
  //   0    → 0.3   плывёт влево по заднему плану, отставая наклоном
  //   0.3  → 0.46  поднимается из-за края и выходит на передний план
  //   0.46 → 0.6   огромное увеличение с замахом вправо
  //   0.6  → 0.72  взмах справа налево: экран закрыт целиком (~0.62–0.78)
  //   0.72 → 0.95  уходит влево вниз, уменьшаясь, открывая новую сцену
  //                справа налево — тот самый "смах"
  const fanDriftY = vh * (low ? 0.9 : 0.7);
  tl.to(st.fan, {
    x: vw * (low ? 0.5 : 0.56),
    y: fanDriftY,
    rotation: 10,
    scale: sc(R0 * 1.12),
    duration: len(0.3),
    ease: "sine.inOut",
  }, at(0))
    .to(st.fan, { opacity: 1, duration: len(0.16) }, at(0.26))
    .to(st.fan, {
      x: vw * 0.555,
      y: fanDriftY + (Py - fanDriftY) * 0.3,
      rotation: 26,
      scale: sc(Math.max(R0 * 2.1, vw * 0.42)),
      duration: len(0.16),
      ease: "sine.in",
    }, at(0.3))
    .set(st.fan, { zIndex: 4 }, at(0.445))
    .to(st.fan, { x: Px, y: Py, rotation: 50, scale: sc(Rc), duration: len(0.14), ease: "power2.in" }, at(0.46))
    .to(st.fan, { rotation: -26, duration: len(0.12) }, at(0.6))
    .to(st.fan, { x: vw * 0.38, rotation: -140, scale: sc(Rc * 0.78), duration: len(0.23), ease: "power2.in" }, at(0.72))
    .set(st.fan, { opacity: 0, zIndex: 1 }, at(0.96));

  // Кастаньеты — на переднем плане, летят влево вместе с веером по дуге,
  // чуть опережая его передний край; приближаются к камере (растут).
  const castPath = low
    ? [[0.2, 0.62, -16], [0.08, 0.42, -40], [-0.35, 0.3, -74]]
    : [[0.62, 0.6, -8], [0.26, 0.4, -34], [-0.2, 0.3, -72]];
  tl.to(st.castanets, {
    x: vw * castPath[0][0], y: vh * castPath[0][1], rotation: castPath[0][2], scale: C * 1.1,
    duration: len(0.33), ease: "sine.inOut",
  }, at(0.12))
    .to(st.castanets, {
      x: vw * castPath[1][0], y: vh * castPath[1][1], rotation: castPath[1][2], scale: C * 1.32,
      duration: len(0.27),
    }, at(0.45))
    .to(st.castanets, {
      x: vw * castPath[2][0], y: vh * castPath[2][1], rotation: castPath[2][2], scale: C * 1.5,
      duration: len(0.2), ease: "power2.in",
    }, at(0.72));
  if (m.soft) tl.to(st.castanets, { filter: "blur(0px)", duration: len(0.22) }, at(0.08));

  // Вся сцена реагирует: софит идёт за веером, луч света клонится,
  // фон "наезжает" камерой; смена фона — строго под полным перекрытием.
  tl.to(st.spot, { x: -vw * 0.22, scale: 1.3, duration: len(0.55), ease: "sine.inOut" }, at(0))
    .to(st.beam, { x: -vw * 0.12, rotation: -9, duration: len(0.6), ease: "sine.inOut" }, at(0))
    .to([st.base, st.floor], { scale: 1.08, duration: len(0.6), ease: "sine.in" }, at(0))
    .to(st.tone, { opacity: 1, duration: len(0.05) }, at(0.645))
    .to(st.vignette, { opacity: 0.3, duration: len(0.05) }, at(0.645));

  const directions = scenes[1];
  directions.layers.forEach((el, k) => {
    if (!isNested(el)) tl.to(el, { opacity: 1, duration: len(0.02) }, at(0.68));
    tl.to(el, { x: 0, scale: 1, duration: len(0.3), ease: "power2.out" }, at(0.7 + k * 0.012));
  });
  tl.to([st.glowA, st.glowB, st.lunares], { x: 0, duration: len(0.3), ease: "power2.out" }, at(0.7));

  // ---------- Средние переходы: панорама камеры влево ----------
  const pan = (seg: Segment) => {
    const out = scenes[seg.scene - 1];
    const inn = scenes[seg.scene];
    const p = (v: number) => seg.start + v * seg.dur;
    const d = (v: number) => v * seg.dur;
    out.layers.forEach((el, k) => {
      const z = depthOf(el);
      tl.to(el, { x: -D * z, scale: 0.97, duration: d(0.62), ease: "power2.in" }, p(0.015 * k));
      if (!isNested(el)) tl.to(el, { opacity: 0, duration: d(0.3), ease: "power1.in" }, p(0.2 + 0.025 * k));
    });
    inn.layers.forEach((el, k) => {
      tl.to(el, { x: 0, scale: 1, duration: d(0.6), ease: "power2.out" }, p(0.38 + 0.015 * k));
      if (!isNested(el)) tl.to(el, { opacity: 1, duration: d(0.3), ease: "power1.out" }, p(0.45 + 0.025 * k));
    });
    // Дальние слои фона — медленнее контента: глубина.
    tl.to(st.glowA, { x: `-=${D * 0.45}`, duration: seg.dur, ease: "sine.inOut" }, seg.start)
      .to(st.glowB, { x: `-=${D * 0.3}`, y: `+=${vh * 0.04}`, duration: seg.dur, ease: "sine.inOut" }, seg.start)
      .to(st.lunares, { x: `-=${D * 0.22}`, duration: seg.dur, ease: "sine.inOut" }, seg.start);
  };
  moves.slice(1, -1).forEach(pan);

  // ---------- Финал: сцена снова темнеет — "после танца" ----------
  {
    const seg = moves[moves.length - 1];
    const out = scenes[seg.scene - 1];
    const inn = scenes[seg.scene];
    const p = (v: number) => seg.start + v * seg.dur;
    const d = (v: number) => v * seg.dur;
    out.layers.forEach((el, k) => {
      const z = depthOf(el);
      tl.to(el, { y: -vh * 0.07 * z, scale: 0.94, duration: d(0.55), ease: "power2.in" }, p(0.015 * k));
      if (!isNested(el)) tl.to(el, { opacity: 0, duration: d(0.3), ease: "power1.in" }, p(0.12 + 0.025 * k));
    });
    tl.to(st.tone, { opacity: 0, duration: d(0.35), ease: "sine.inOut" }, p(0.25))
      .to(st.vignette, { opacity: 1, duration: d(0.35) }, p(0.25))
      .to(st.spot, { x: 0, scale: 1, duration: d(0.6), ease: "sine.out" }, p(0.3))
      .to(st.beam, { x: 0, rotation: 4, duration: d(0.6), ease: "sine.out" }, p(0.3))
      .to([st.base, st.floor], { scale: 1, duration: d(0.6), ease: "sine.out" }, p(0.3));

    // Веер поднимается снизу на своё место из hero — финальная поза,
    // кастаньеты ложатся рядом: композиция замыкается на начало.
    tl.set(st.fan, { x: fanHome.x, y: vh * 1.45, rotation: -40, scale: sc(R0 * 0.95), opacity: 0.9, zIndex: 1 }, p(0.2))
      .to(st.fan, { y: fanHome.y, rotation: fanHome.rotation + 2, duration: d(0.65), ease: "power3.out" }, p(0.32));
    tl.set(st.castanets, { x: vw * 1.2, y: vh * 0.98, rotation: 50, scale: C * 0.9 }, p(0.2))
      .to(st.castanets, {
        x: castHome.x, y: castHome.y, rotation: castHome.rotation - 4,
        duration: d(0.6), ease: "power2.out",
      }, p(0.4));
    if (m.soft) tl.set(st.castanets, { filter: "blur(2px)" }, p(0.2));

    inn.layers.forEach((el, k) => {
      tl.to(el, { y: 0, duration: d(0.55), ease: "power2.out" }, p(0.42 + 0.015 * k));
      if (!isNested(el)) tl.to(el, { opacity: 1, duration: d(0.3), ease: "power1.out" }, p(0.48 + 0.025 * k));
    });
  }

  // ---------- Удержания: дрейф и прокрутка высокого контента ----------
  segments.forEach((seg) => {
    if (seg.kind !== "hold" || seg.dur <= 0) return;
    const scene = scenes[seg.scene];
    const edge = seg.scene === 0 || seg.scene === lastIndex ? 0 : drift;
    tl.to(scene.scroller, { y: -scene.overflow - edge, duration: seg.dur }, seg.start);
  });

  tl.set({}, {}, duration);

  return {
    tl,
    duration,
    segments,
    settle,
    activeAt: (t) => {
      let i = 0;
      while (i < boundaries.length && t >= boundaries[i]) i++;
      return i;
    },
    fan: { start: T0.start, end: T0.start + T0.dur, snapFrom: at(0.45), snapTo: at(0.9) },
    locate: (t) => {
      for (let i = segments.length - 1; i >= 0; i--) {
        const s = segments[i];
        if (t >= s.start) return { seg: i, frac: s.dur > 0 ? Math.min(1, (t - s.start) / s.dur) : 0 };
      }
      return { seg: 0, frac: 0 };
    },
    timeAt: ({ seg, frac }) => {
      const s = segments[Math.min(seg, segments.length - 1)];
      return s.start + s.dur * frac;
    },
  };
}
