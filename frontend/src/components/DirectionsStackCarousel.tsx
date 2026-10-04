"use client";

import Link from "next/link";
import { useState } from "react";
import type { Direction } from "@/lib/directions";

const CARD_WIDTH = 288;
// Шаг смещения для 1-го и 2-го плана. Должен быть больше половины ширины
// активной карточки (144px) плюс половины уменьшенной соседней — иначе
// полупрозрачные glass-medium карточки накладываются друг на друга и текст
// соседней карточки просвечивает поверх активной (было на реальных данных:
// карточки стояли почти вплотную и читались одновременно).
const OFFSET_STEP = [0, 300, 480];

// Карусель с наложением: активная карточка по центру в полный размер, соседние
// видны по бокам — уменьшены, затемнены и слегка размыты позади неё. Листать
// можно только стрелками рядом с активной карточкой (по боковым карточкам не
// кликнуть — иначе их ссылку/кнопку внутри было бы невозможно нажать).
export function DirectionsStackCarousel({ directions }: { directions: Direction[] }) {
  const [active, setActive] = useState(0);

  // Без направлений (каталог недоступен) секция раньше оставалась пустой —
  // заголовок без единой карточки, будто страница сломана. Показываем то же
  // объяснение, что и для пустого расписания (см. EmptyScheduleNotice).
  if (directions.length === 0) {
    return (
      <div className="glass-medium mx-auto flex max-w-xl flex-col items-center gap-3 rounded-[24px] p-6 text-center">
        <p className="text-[var(--text-secondary)]">
          Каталог направлений сейчас недоступен. Попробуйте обновить страницу
          позже.
        </p>
      </div>
    );
  }

  const goTo = (index: number) => {
    setActive((index + directions.length) % directions.length);
  };

  return (
    <div
      className="relative flex h-[440px] items-center justify-center overflow-hidden"
      style={{ perspective: "1200px" }}
    >
      {directions.length > 1 && (
        <>
          <button
            type="button"
            onClick={() => goTo(active - 1)}
            aria-label="Предыдущее направление"
            className="glass-subtle glass-float glass-interactive absolute top-1/2 z-20 flex h-10 w-10 items-center justify-center rounded-full text-lg text-[var(--text-primary)] hover:text-[var(--primary)]"
            style={{ left: "50%", transform: `translate(calc(-50% - ${CARD_WIDTH / 2 + 24}px), -50%)` }}
          >
            ‹
          </button>
          <button
            type="button"
            onClick={() => goTo(active + 1)}
            aria-label="Следующее направление"
            className="glass-subtle glass-float glass-interactive absolute top-1/2 z-20 flex h-10 w-10 items-center justify-center rounded-full text-lg text-[var(--text-primary)] hover:text-[var(--primary)]"
            style={{ left: "50%", transform: `translate(calc(-50% + ${CARD_WIDTH / 2 + 24}px), -50%)` }}
          >
            ›
          </button>
        </>
      )}

      {directions.map((direction, index) => {
        let offset = index - active;
        // Закольцовываем: направление через край считаем ближайшим соседом.
        if (offset > directions.length / 2) offset -= directions.length;
        if (offset < -directions.length / 2) offset += directions.length;

        const abs = Math.abs(offset);
        if (abs > 2) return null;

        const step = OFFSET_STEP[abs];
        const translateX = offset === 0 ? 0 : offset > 0 ? step : -step;
        const scale = abs === 0 ? 1 : abs === 1 ? 0.85 : 0.72;
        const opacity = abs === 0 ? 1 : abs === 1 ? 0.45 : 0.22;
        const blur = abs === 0 ? 0 : abs === 1 ? 3 : 5;
        // Держим z-index заметно ниже шапки (z-10, sticky), иначе при
        // минимальной прокрутке карточки рисуются поверх неё.
        const zIndex = 5 - abs;

        const isActive = offset === 0;

        return (
          <div
            key={direction.key}
            aria-hidden={!isActive}
            className="glass-medium absolute top-1/2 left-1/2 flex w-72 flex-col gap-3 rounded-[28px] p-7"
            style={{
              transform: `translate(-50%, -50%) translateX(${translateX}px) scale(${scale})`,
              opacity,
              filter: blur ? `blur(${blur}px)` : undefined,
              zIndex,
              // Карточка, становящаяся активной, слегка "пружинит" на месте
              // (overshoot) — так смена видна отчётливее, чем ровный ease-out.
              // Для уходящих в сторону карточек — обычное плавное замедление,
              // overshoot на уменьшении смотрелся бы как дрожание.
              transition: isActive
                ? "transform 550ms cubic-bezier(0.34, 1.56, 0.64, 1), opacity 450ms ease-out, filter 450ms ease-out"
                : "transform 500ms ease-out, opacity 450ms ease-out, filter 450ms ease-out",
            }}
          >
            <div>
              <h2 className="font-heading mb-2 text-xl font-bold tracking-tight">{direction.label}</h2>
              <span className="inline-block rounded-full bg-[var(--primary-light)] px-3 py-0.5 text-xs font-semibold text-[var(--accent-dark)]">
                {direction.level}
              </span>
            </div>
            <p className="text-base leading-relaxed text-[var(--text-secondary)]">
              {direction.description}
            </p>
            <Link
              href={`/schedule?class_key=${direction.key}`}
              tabIndex={isActive ? undefined : -1}
              className="mt-auto inline-flex items-center justify-center gap-1.5 rounded-full bg-[var(--primary)] px-4 py-2.5 text-sm font-semibold text-[var(--on-primary)] shadow-[var(--shadow-card)] transition hover:bg-[var(--primary-hover)] hover:shadow-[var(--shadow-card-hover)]"
            >
              Смотреть расписание →
            </Link>
          </div>
        );
      })}
    </div>
  );
}
