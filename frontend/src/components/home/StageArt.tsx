// Векторные объекты сцены главной: кастаньеты, роза, лепестки. Нарисованы
// для этого проекта (лицензионно чистые, см. public/assets/CREDITS.md).
// Веер — не вектор, а отдельный фотографический ассет
// (public/assets/objects/fan.webp, см. CREDITS.md) — рисованный веер
// заменён на него по прямому запросу.
//
// Градиенты объявлены один раз в <StageArtDefs/> и доступны остальным
// инлайновым SVG документа по id — без хуков, рендерится на сервере.

export function StageArtDefs() {
  return (
    <svg width="0" height="0" className="absolute" aria-hidden="true" focusable="false">
      <defs>
        <radialGradient id="st-castanet" cx="0.38" cy="0.32" r="0.75">
          <stop offset="0" stopColor="#8A4B2A" />
          <stop offset="0.45" stopColor="#4A2213" />
          <stop offset="1" stopColor="#1A0A05" />
        </radialGradient>
        <radialGradient id="st-petal" cx="0.4" cy="0.3" r="0.9">
          <stop offset="0" stopColor="#E8455F" />
          <stop offset="0.6" stopColor="#A90F2C" />
          <stop offset="1" stopColor="#5C0715" />
        </radialGradient>
        <radialGradient id="st-rose-core" cx="0.5" cy="0.45" r="0.6">
          <stop offset="0" stopColor="#3D0410" />
          <stop offset="1" stopColor="#8E0C25" />
        </radialGradient>
        <linearGradient id="st-leaf-green" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#3F5F2A" />
          <stop offset="1" stopColor="#1C2E12" />
        </linearGradient>
      </defs>
    </svg>
  );
}

export function CastanetsArt() {
  const shell = "M0 -70 C 48 -70 76 -36 76 6 C 76 52 42 86 0 86 C -42 86 -76 52 -76 6 C -76 -36 -48 -70 0 -70 Z";
  return (
    <svg viewBox="-170 -150 340 290" className="h-full w-full overflow-visible" aria-hidden="true">
      <path d="M -40 -88 C -70 -150 40 -160 30 -100 C 24 -66 64 -92 72 -112" stroke="#B3122E" strokeWidth="7" fill="none" strokeLinecap="round" />
      <path d="M -40 -88 C -70 -150 40 -160 30 -100" stroke="#E8455F" strokeWidth="2" fill="none" opacity="0.6" />
      <g transform="translate(-58 6) rotate(-14)">
        <path d={shell} fill="url(#st-castanet)" />
        <path d="M -44 -40 C -30 -60 10 -66 32 -50" stroke="#C99A6A" strokeWidth="5" fill="none" opacity="0.45" strokeLinecap="round" />
        <circle cx="0" cy="-58" r="7" fill="#120603" />
      </g>
      <g transform="translate(58 18) rotate(12)">
        <path d={shell} fill="url(#st-castanet)" />
        <path d="M -44 -40 C -30 -60 10 -66 32 -50" stroke="#C99A6A" strokeWidth="5" fill="none" opacity="0.45" strokeLinecap="round" />
        <circle cx="0" cy="-58" r="7" fill="#120603" />
      </g>
    </svg>
  );
}

export function RoseArt() {
  const petal = (r: number, rot: number, fill: string) => (
    <path
      key={`${r}-${rot}`}
      transform={`rotate(${rot})`}
      d={`M 0 ${-r} C ${r * 0.9} ${-r * 0.95} ${r * 1.05} ${r * 0.1} 0 ${r * 0.35} C ${-r * 1.05} ${r * 0.1} ${-r * 0.9} ${-r * 0.95} 0 ${-r} Z`}
      fill={fill}
    />
  );
  return (
    <svg viewBox="-120 -120 240 240" className="h-full w-full overflow-visible" aria-hidden="true">
      <path d="M -10 40 C -60 60 -100 40 -110 10 C -70 0 -30 10 -10 40 Z" fill="url(#st-leaf-green)" />
      <path d="M 14 44 C 60 74 100 60 112 30 C 70 18 34 26 14 44 Z" fill="url(#st-leaf-green)" />
      {[0, 72, 144, 216, 288].map((a) => petal(78, a + 18, "url(#st-petal)"))}
      {[0, 90, 180, 270].map((a) => petal(58, a + 45, "#9E0E2A"))}
      {[0, 120, 240].map((a) => petal(40, a, "url(#st-petal)"))}
      {[60, 180, 300].map((a) => petal(26, a, "#7A0A1F"))}
      <circle r="14" fill="url(#st-rose-core)" />
      <path d="M -8 -4 C -2 -14 10 -10 8 0 C 6 8 -6 8 -4 0" stroke="#E8455F" strokeWidth="2.5" fill="none" opacity="0.7" />
    </svg>
  );
}

export function PetalArt() {
  return (
    <svg viewBox="-30 -40 60 80" className="h-full w-full overflow-visible" aria-hidden="true">
      <path d="M 0 -36 C 26 -30 30 10 0 36 C -30 10 -26 -30 0 -36 Z" fill="url(#st-petal)" />
      <path d="M 0 -30 C 6 -8 6 12 0 30" stroke="#F06A80" strokeWidth="1.5" fill="none" opacity="0.5" />
    </svg>
  );
}
