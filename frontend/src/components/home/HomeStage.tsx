import { CastanetsArt, FanArt } from "./StageArt";

// Сцена главной — всё, что позади и вокруг контента (aria-hidden: смысл
// страницы несут сами сцены с текстом и кнопками).
//
//   .stage            фон, сзади: база → пол → софит → луч света → тон
//                     средних сцен (с бликами и горошком) → виньетка
//   .stage-fan        веер — отдельно от .stage, чтобы в переходе Hero →
//                     Направления менять его z-index относительно слоя сцен
//                     (выходит из фона на передний план)
//   .stage-castanets  кастаньеты — всегда на переднем плане
//
// Статичное CSS-положение каждого слоя = кадр hero (scroll progress 0):
// так страница выглядит осмысленно без JS и при prefers-reduced-motion.
// Хореография (state = f(scroll progress)) — choreography.ts, элементы
// ищутся по data-st.

export function HomeStage() {
  return (
    <>
      <div className="stage" aria-hidden="true">
        <div className="stage-base" data-st="base" />
        <div className="stage-floor" data-st="floor" />
        <div className="stage-spot" data-st="spot" />
        <div className="stage-beam" data-st="beam" />
        <div className="stage-tone" data-st="tone">
          <div className="stage-glow stage-glow--wine" data-st="glow-a" />
          <div className="stage-glow stage-glow--rose" data-st="glow-b" />
          <div className="stage-lunares" data-st="lunares" />
        </div>
        <div className="stage-vignette" data-st="vignette" />
      </div>

      <div className="stage-anchor stage-fan" data-st="fan" aria-hidden="true">
        <div className="stage-fan-swing" data-st="fan-swing">
          <FanArt className="stage-fan-art" />
        </div>
      </div>

      <div className="stage-anchor stage-castanets" data-st="castanets" aria-hidden="true">
        <div className="stage-castanets-spin" data-st="castanets-spin">
          <CastanetsArt className="stage-castanets-art" />
        </div>
      </div>
    </>
  );
}
