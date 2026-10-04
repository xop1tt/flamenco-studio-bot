// Слои сцены главной (сзади → вперёд): база → софит → тон темы →
// виньетка. Всё — визуал, aria-hidden: смысл страницы несёт
// контентный слой поверх (заголовки, кнопки, карточки). Статичное
// положение каждого слоя в CSS = кадр progress 0 (hero) — так страница
// выглядит осмысленно без JS и при prefers-reduced-motion. Хореография
// (state = f(scrollProgress)) — в HomeStory, элементы ищутся по data-st.
// Ассеты и лицензии — public/assets/CREDITS.md.

export function HomeStage() {
  return (
    <div className="stage" data-st="stage" aria-hidden="true">
      <div className="stage-base" />
      <div className="stage-spot" data-st="spot" />

      {/* Атмосфера средних сцен (About → Schedule) — тон темы сайта, без
          отдельной фоновой фотографии: градиентный glow + лёгкий
          hue-shift, оба привязаны к scroll progress (см. HomeStory). */}
      <div className="stage-tone" data-st="tone">
        <div className="stage-tone-glow" data-st="tone-glow" />
      </div>

      <div className="stage-vignette" />
    </div>
  );
}
