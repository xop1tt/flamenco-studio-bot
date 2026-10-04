/**
 * Направления занятий для сайта.
 *
 * Название, описание и уровень приходят с backend (`GET /api/classes`,
 * источник истины — `src/flamenco_bot/class_catalog.py`, тот же каталог,
 * которым пользуется бот), поэтому на сайте и в боте текст одинаковый.
 */

import { getClasses } from "./api";

export type Direction = {
  key: string;
  label: string;
  description: string;
  level: string;
};

export async function getDirections(): Promise<Direction[]> {
  const classes = await getClasses();
  return classes.map((item) => ({
    key: item.key,
    label: item.label,
    description: item.description,
    level: item.level,
  }));
}
