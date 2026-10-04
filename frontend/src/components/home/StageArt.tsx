// Векторный реквизит сцены главной: веер и кастаньеты. Нарисованы для этого
// проекта, без фотографической основы (см. public/assets/CREDITS.md).
//
// Веер — вектор, а не фото, намеренно: в переходе Hero → Направления он
// вырастает до размера, закрывающего весь экран (×4 к исходному), и
// растровый ассет на таком масштабе превращался бы в мыло. Разметка
// считается здесь, на сервере, один раз — в клиентский бандл уходит
// только готовый SVG.

import {
  FAN_BOX,
  FAN_HALF,
  FAN_PLEATS,
  FAN_R,
  FAN_RI,
} from "./fanGeometry";

const rad = (deg: number) => (deg * Math.PI) / 180;
const n = (v: number) => Math.round(v * 10) / 10;
// Точка на радиусе r под углом deg от вертикали (по часовой) — в "x y".
const P = (r: number, deg: number) => `${n(r * Math.sin(rad(deg)))} ${n(-r * Math.cos(rad(deg)))}`;

const STEP = (FAN_HALF * 2) / FAN_PLEATS;
const RIBS = Array.from({ length: FAN_PLEATS + 1 }, (_, k) => -FAN_HALF + k * STEP);
// Складка: гребень на пластине (радиус R), впадина посередине (чуть ниже).
const VALLEY = 22;
const LACE = 62;

function leafFaces() {
  const lit: string[] = [];
  const shade: string[] = [];
  for (let k = 0; k < FAN_PLEATS; k++) {
    const a = RIBS[k];
    const b = RIBS[k + 1];
    const m = (a + b) / 2;
    // Свет слева сверху: грань, обращённая влево (впадина → гребень
    // справа), светлее; соседняя — в тени.
    shade.push(`M${P(FAN_RI, a)}L${P(FAN_R, a)}L${P(FAN_R - VALLEY, m)}L${P(FAN_RI - 8, m)}Z`);
    lit.push(`M${P(FAN_RI - 8, m)}L${P(FAN_R - VALLEY, m)}L${P(FAN_R, b)}L${P(FAN_RI, b)}Z`);
  }
  return { lit: lit.join(""), shade: shade.join("") };
}

// Контур всего листа — для общего блика поверх граней.
function leafOutline() {
  let d = `M${P(FAN_RI, -FAN_HALF)}L${P(FAN_R, -FAN_HALF)}`;
  for (let k = 0; k < FAN_PLEATS; k++) {
    const m = (RIBS[k] + RIBS[k + 1]) / 2;
    d += `L${P(FAN_R - VALLEY, m)}L${P(FAN_R, RIBS[k + 1])}`;
  }
  d += `L${P(FAN_RI, FAN_HALF)}A${FAN_RI} ${FAN_RI} 0 0 0 ${P(FAN_RI, -FAN_HALF)}Z`;
  return d;
}

// Чёрное кружево по краю: внешний край — фестоны (по два на грань),
// внутренний повторяет зигзаг складок.
function laceBand() {
  const outer: [number, number][] = [];
  for (let k = 0; k < FAN_PLEATS; k++) {
    const a = RIBS[k];
    const m = (a + RIBS[k + 1]) / 2;
    outer.push([FAN_R, a], [FAN_R - VALLEY, m]);
  }
  outer.push([FAN_R, FAN_HALF]);

  let d = `M${P(outer[0][0], outer[0][1])}`;
  for (let i = 1; i < outer.length; i++) {
    const [r0, a0] = outer[i - 1];
    const [r1, a1] = outer[i];
    const mid: [number, number] = [(r0 + r1) / 2, (a0 + a1) / 2];
    for (const [r, a] of [mid, [r1, a1] as [number, number]]) {
      d += `A16 16 0 0 1 ${P(r, a)}`;
    }
  }
  for (let i = outer.length - 1; i >= 0; i--) {
    const [r, a] = outer[i];
    d += `L${P(r - LACE, a)}`;
  }
  return `${d}Z`;
}

function lacePolyline(offset: number) {
  const pts: string[] = [];
  for (let k = 0; k < FAN_PLEATS; k++) {
    const a = RIBS[k];
    const m = (a + RIBS[k + 1]) / 2;
    pts.push(P(FAN_R - offset, a), P(FAN_R - VALLEY - offset, m));
  }
  pts.push(P(FAN_R - offset, FAN_HALF));
  return pts.join(" ");
}

// Лунарес — горошек фламенко: ряды по радиусу с шахматным сдвигом,
// шаг по дуге примерно постоянный, как у принта на ткани.
function lunares() {
  const dots: { cx: number; cy: number; r: number; lit: boolean }[] = [];
  const rows = [490, 575, 660, 745, 830];
  rows.forEach((radius, row) => {
    const spacing = (118 / radius) * (180 / Math.PI);
    const start = -FAN_HALF + 4 + (row % 2 ? spacing / 2 : 0);
    for (let a = start; a <= FAN_HALF - 4; a += spacing) {
      const within = (a + FAN_HALF) % STEP;
      dots.push({
        cx: n(radius * Math.sin(rad(a))),
        cy: n(-radius * Math.cos(rad(a))),
        r: n(radius * 0.026),
        lit: within >= STEP / 2,
      });
    }
  });
  return dots;
}

function stick(angle: number, r0: number, r1: number, w0: number, w1: number) {
  const s = Math.sin(rad(angle));
  const c = Math.cos(rad(angle));
  const pt = (r: number, off: number) => `${n(r * s + off * c)} ${n(-r * c + off * s)}`;
  return `M${pt(r0, -w0 / 2)}L${pt(r1, -w1 / 2)}L${pt(r1, w1 / 2)}L${pt(r0, w0 / 2)}Z`;
}

const FACES = leafFaces();
const OUTLINE = leafOutline();
const LACE_BAND = laceBand();
const LACE_EDGE = lacePolyline(LACE);
const DOTS = lunares();
const INNER_EDGE = RIBS.map((a, k) =>
  k < RIBS.length - 1 ? `${P(FAN_RI, a)} ${P(FAN_RI - 8, (a + RIBS[k + 1]) / 2)}` : P(FAN_RI, a),
).join(" ");

export function FanArt({ className }: { className?: string }) {
  return (
    <svg
      viewBox={`${FAN_BOX.x} ${FAN_BOX.y} ${FAN_BOX.w} ${FAN_BOX.h}`}
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <radialGradient id="fan-lit" cx="0" cy="0" r={FAN_R} gradientUnits="userSpaceOnUse">
          <stop offset={FAN_RI / FAN_R} stopColor="#8a1426" />
          <stop offset="0.72" stopColor="#b3182f" />
          <stop offset="1" stopColor="#c8263c" />
        </radialGradient>
        <radialGradient id="fan-shade" cx="0" cy="0" r={FAN_R} gradientUnits="userSpaceOnUse">
          <stop offset={FAN_RI / FAN_R} stopColor="#4f0813" />
          <stop offset="0.72" stopColor="#6e0d1d" />
          <stop offset="1" stopColor="#821324" />
        </radialGradient>
        <linearGradient id="fan-sheen" x1="-900" y1="-1000" x2="700" y2="80" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#fff" stopOpacity="0.2" />
          <stop offset="0.42" stopColor="#fff" stopOpacity="0" />
          <stop offset="1" stopColor="#000" stopOpacity="0.28" />
        </linearGradient>
        <linearGradient id="fan-lacquer" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#140405" />
          <stop offset="0.5" stopColor="#4a1915" />
          <stop offset="1" stopColor="#140405" />
        </linearGradient>
        <radialGradient id="fan-rivet" cx="0.38" cy="0.32" r="0.8">
          <stop offset="0" stopColor="#f6e2b6" />
          <stop offset="0.5" stopColor="#b98a4b" />
          <stop offset="1" stopColor="#4f3215" />
        </radialGradient>
      </defs>

      {/* Пластины (варильяс) под листом — между ними просветы. */}
      <g fill="#250a0b" stroke="#4a1a17" strokeWidth="2">
        {RIBS.slice(1, -1).map((a) => (
          <path key={a} d={stick(a, 40, FAN_RI + 16, 20, 12)} />
        ))}
      </g>

      {/* Лист: грани складок, горошек, общий атласный блик. */}
      <path d={FACES.shade} fill="url(#fan-shade)" />
      <path d={FACES.lit} fill="url(#fan-lit)" />
      <g>
        {DOTS.map((dot) => (
          <circle key={`${dot.cx},${dot.cy}`} cx={dot.cx} cy={dot.cy} r={dot.r} fill={dot.lit ? "#f8ebdd" : "#d9c1b0"} />
        ))}
      </g>
      <g stroke="#ffd8cc" strokeOpacity="0.16" strokeWidth="3">
        {RIBS.slice(1, -1).map((a) => (
          <path key={a} d={`M${P(FAN_RI, a)}L${P(FAN_R - LACE, a)}`} />
        ))}
      </g>
      <path d={OUTLINE} fill="url(#fan-sheen)" />

      {/* Кружево по краю и тонкие золотые линии кромки. */}
      <path d={LACE_BAND} fill="#1a0307" />
      <g fill="#5e0f1b">
        {RIBS.slice(0, -1).map((a) => (
          <circle key={a} cx={n((FAN_R - 34) * Math.sin(rad(a + STEP / 2)))} cy={n(-(FAN_R - 34) * Math.cos(rad(a + STEP / 2)))} r="7" />
        ))}
      </g>
      <polyline points={LACE_EDGE} fill="none" stroke="#c79c5e" strokeOpacity="0.6" strokeWidth="3" />
      <polyline points={INNER_EDGE} fill="none" stroke="#c79c5e" strokeOpacity="0.45" strokeWidth="3" />

      {/* Крайние пластины (гуарды) поверх листа и головка с заклёпкой. */}
      {[-FAN_HALF - 1.4, FAN_HALF + 1.4].map((a) => (
        <g key={a}>
          <path d={stick(a, -36, FAN_R + 12, 34, 20)} fill="url(#fan-lacquer)" stroke="#5a221c" strokeWidth="2" />
          <path d={stick(a, FAN_RI, FAN_R - 30, 4, 3)} fill="#c79c5e" fillOpacity="0.55" />
        </g>
      ))}
      <circle cx="0" cy="8" r="46" fill="#1d0607" stroke="#5a221c" strokeWidth="3" />
      <circle cx="0" cy="0" r="18" fill="url(#fan-rivet)" />
      <circle cx="-5" cy="-6" r="5" fill="#fff" fillOpacity="0.55" />
    </svg>
  );
}

export function CastanetsArt({ className }: { className?: string }) {
  // Половинка кастаньеты спереди: округлая чаша (тыльная сторона) с
  // широким "ушком" сверху — частью того же дерева, с отверстием, через
  // которое проходит шнур, связывающий пару.
  const shell =
    "M-34 -98 C -34 -107 34 -107 34 -98 L 36 -84 C 66 -76 84 -44 84 2 C 84 50 48 86 0 86 C -48 86 -84 50 -84 2 C -84 -44 -66 -76 -36 -84 Z";
  const half = (dx: number, dy: number, rot: number, key: string) => (
    <g key={key} transform={`translate(${dx} ${dy}) rotate(${rot})`}>
      <path d={shell} fill="url(#cast-wood)" stroke="#120603" strokeWidth="2" />
      <g fill="none" stroke="#e0a77a" strokeOpacity="0.07" strokeWidth="3">
        <path d="M-66 -10 C -36 -36 36 -36 66 -10" />
        <path d="M-74 26 C -40 2 40 2 74 26" />
        <path d="M-58 58 C -30 40 30 40 58 58" />
      </g>
      {/* Кромка чаши — светлый серп по левому краю даёт толщину дерева. */}
      <path d="M-66 -46 C -82 -4 -70 44 -34 72" stroke="#f0c39b" strokeOpacity="0.2" strokeWidth="5" fill="none" strokeLinecap="round" />
      <ellipse cx="-28" cy="-34" rx="14" ry="26" transform="rotate(-34 -28 -34)" fill="#fff" fillOpacity="0.13" />
      <ellipse cx="0" cy="-93" rx="7" ry="4" fill="#0b0302" />
    </g>
  );

  return (
    <svg viewBox="-180 -170 360 300" className={className} aria-hidden="true" focusable="false">
      <defs>
        <radialGradient id="cast-wood" cx="0.34" cy="0.3" r="0.85">
          <stop offset="0" stopColor="#8a4424" />
          <stop offset="0.5" stopColor="#3a160a" />
          <stop offset="1" stopColor="#120603" />
        </radialGradient>
      </defs>
      {half(-60, 8, -14, "l")}
      {half(60, 20, 12, "r")}
      {/* Шнур — красный: продет сквозь ушки обеих половинок, сверху —
          петля под большой палец танцовщицы. */}
      <g fill="none" strokeLinecap="round">
        <path d="M -100 -84 C -60 -92 50 -84 96 -68" stroke="#9e1029" strokeWidth="7" />
        <path d="M -12 -86 C -40 -150 40 -156 16 -84" stroke="#9e1029" strokeWidth="6" />
        <path d="M -100 -84 C -60 -92 50 -84 96 -68" stroke="#e8455f" strokeWidth="2" strokeOpacity="0.5" />
        <path d="M -12 -86 C -40 -150 40 -156 16 -84" stroke="#e8455f" strokeWidth="1.6" strokeOpacity="0.45" />
      </g>
    </svg>
  );
}
