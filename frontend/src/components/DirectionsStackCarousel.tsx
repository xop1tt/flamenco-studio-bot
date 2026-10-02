"use client";

import Link from "next/link";
import { useState } from "react";
import type { Direction } from "@/lib/directions";

const CARD_WIDTH = 288;
// Шаг смещения для 1-го и 2-го плана — специально нелинейный и пошире, чтобы
// задние карточки заметно выглядывали по бокам и было понятно, что их можно
// пролистать.
const OFFSET_STEP = [0, 190, 330];

// Карусель с наложением: активная карточка по центру в полный размер, соседние
// видны по бокам — уменьшены, затемнены и слегка размыты позади неё. Листать
// можно только стрелками рядом с активной карточкой (по боковым карточкам не
// кликнуть — иначе их ссылку/кнопку внутри было бы невозможно нажать).
export function DirectionsStackCarousel({ directions }: { directions: Direction[] }) {
  const [active, setActive] = useState(0);

  if (directions.length === 0) {
    return null;
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
            className="absolute top-1/2 z-20 flex h-10 w-10 items-center justify-center rounded-full bg-[var(--text-primary)]/55 text-lg text-[var(--surface)] transition hover:bg-[var(--text-primary)]/75"
            style={{ left: "50%", transform: `translate(calc(-50% - ${CARD_WIDTH / 2 + 24}px), -50%)` }}
          >
            ‹
          </button>
          <button
            type="button"
            onClick={() => goTo(active + 1)}
            aria-label="Следующее направление"
            className="absolute top-1/2 z-20 flex h-10 w-10 items-center justify-center rounded-full bg-[var(--text-primary)]/55 text-lg text-[var(--surface)] transition hover:bg-[var(--text-primary)]/75"
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
        const opacity = abs === 0 ? 1 : abs === 1 ? 0.65 : 0.35;
        const blur = abs === 0 ? 0 : abs === 1 ? 1.5 : 3;
        // Держим z-index заметно ниже шапки (z-10, sticky), иначе при
        // минимальной прокрутке карточки рисуются поверх неё.
        const zIndex = 5 - abs;

        const isActive = offset === 0;

        return (
          <div
            key={direction.key}
            aria-hidden={!isActive}
            className="glass-card absolute top-1/2 left-1/2 flex w-72 flex-col gap-3 rounded-2xl p-6 shadow-[var(--shadow-card-hover)] transition-all duration-500 ease-out"
            style={{
              transform: `translate(-50%, -50%) translateX(${translateX}px) scale(${scale})`,
              opacity,
              filter: blur ? `blur(${blur}px)` : undefined,
              zIndex,
            }}
          >
            <div>
              <h2 className="mb-1 text-xl font-semibold">{direction.label}</h2>
              <span className="inline-block rounded-full bg-[var(--primary-light)] px-3 py-0.5 text-xs font-semibold text-[var(--accent-dark)]">
                {direction.level}
              </span>
            </div>
            <p className="text-base leading-relaxed text-[var(--text-secondary)]">
              {direction.description}
            </p>
            <dl className="flex flex-col gap-1 text-sm text-[var(--text-secondary)]">
              <div className="flex justify-between gap-2">
                <dt className="text-[var(--text-primary)]">Длительность</dt>
                <dd>уточняется</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-[var(--text-primary)]">Дни и время</dt>
                <dd>см. расписание</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-[var(--text-primary)]">Группа</dt>
                <dd>уточняется</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-[var(--text-primary)]">Обувь/форма</dt>
                <dd>уточняется</dd>
              </div>
            </dl>
            <Link
              href={`/schedule?class_key=${direction.key}`}
              tabIndex={isActive ? undefined : -1}
              className="mt-auto inline-flex items-center justify-center gap-1.5 rounded-full bg-[var(--primary)] px-4 py-2.5 text-sm font-semibold text-[var(--surface)] shadow-[var(--shadow-card)] transition hover:bg-[var(--primary-hover)] hover:shadow-[var(--shadow-card-hover)]"
            >
              Смотреть расписание →
            </Link>
          </div>
        );
      })}
    </div>
  );
}
