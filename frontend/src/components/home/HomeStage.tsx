import { CastanetsArt, PetalArt, RoseArt, StageArtDefs } from "./StageArt";

// Слои сцены главной (сзади → вперёд): база → дымка → софит → тон темы →
// типографика → веер → кастаньеты/роза/лепестки → виньетка. Всё — визуал,
// aria-hidden: смысл страницы несёт контентный слой поверх (заголовки,
// кнопки, карточки). Статичное положение каждого слоя в CSS = кадр
// progress 0 (hero) — так страница выглядит осмысленно без JS и при
// prefers-reduced-motion. Хореография (state = f(scrollProgress)) — в
// HomeStory, элементы ищутся по data-st. Ассеты и лицензии —
// public/assets/CREDITS.md.

// Разлёт лепестков от веера в разные стороны.
export const PETALS = [
  { size: 4.2, to: [8, 18], spin: 220, blur: 0 },
  { size: 2.6, to: [38, 6], spin: -160, blur: 0 },
  { size: 5.6, to: [-6, 64], spin: 300, blur: 2.5 },
  { size: 3.2, to: [56, 2], spin: -260, blur: 0 },
  { size: 2.2, to: [84, 12], spin: 180, blur: 0 },
  { size: 6.4, to: [26, 108], spin: -320, blur: 3 },
  { size: 3.6, to: [104, 40], spin: 240, blur: 1 },
] as const;

export function HomeStage() {
  return (
    <div className="stage" data-st="stage" aria-hidden="true">
      <StageArtDefs />

      <div className="stage-base" />
      <div className="stage-haze" data-st="haze">
        {/* eslint-disable-next-line @next/next/no-img-element -- фон уже ужат под размер, next/image ничего не даёт фиксированному слою */}
        <img src="/assets/backgrounds/stage-haze.webp" alt="" decoding="async" />
      </div>
      <div className="stage-spot" data-st="spot" />

      {/* Атмосфера средних сцен (About → Schedule) — тон темы сайта, без
          отдельной фоновой фотографии: градиентный glow + лёгкий
          hue-shift, оба привязаны к scroll progress (см. HomeStory). */}
      <div className="stage-tone" data-st="tone">
        <div className="stage-tone-glow" data-st="tone-glow" />
      </div>

      <div className="stage-type" data-st="type">Flamenco</div>

      <div className="stage-anchor stage-fan" data-st="fan">
        {/* eslint-disable-next-line @next/next/no-img-element -- см. выше */}
        <img
          src="/assets/objects/fan.webp"
          alt=""
          className="stage-fan-art"
          fetchPriority="high"
          decoding="async"
        />
      </div>

      <div className="stage-anchor stage-castanets" data-st="castanets">
        <div className="stage-object-art">
          <CastanetsArt />
        </div>
      </div>

      <div className="stage-anchor stage-rose" data-st="rose">
        <div className="stage-object-art">
          <RoseArt />
        </div>
      </div>

      {PETALS.map((petal, i) => (
        <div
          key={i}
          className="stage-anchor stage-petal"
          data-st="petal"
          style={{ "--petal-size": `${petal.size}vh` } as React.CSSProperties}
        >
          <div className="stage-object-art">
            <PetalArt />
          </div>
        </div>
      ))}

      <div className="stage-vignette" />
    </div>
  );
}
