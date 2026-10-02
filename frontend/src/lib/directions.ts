/**
 * Описания направлений занятий — маркетинговый текст для сайта.
 *
 * `key`/`label` приходят с backend (`GET /api/classes`, источник истины —
 * `CLASS_LABELS` в `src/flamenco_bot/class_catalog.py`, тот же словарь,
 * которым пользуется бот) — здесь хранится только `description`,
 * маркетинговый текст, которого в каталоге бэкенда нет и не должно быть.
 */

import { getClasses } from "./api";

export type Direction = {
  key: string;
  label: string;
  description: string;
};

const DESCRIPTIONS: Record<string, string> = {
  beginner:
    "Группа для тех, кто никогда не танцевал фламенко или делает первые " +
    "шаги. Базовая техника, ритм, работа с телом — без предварительной " +
    "подготовки.",
  intermediate:
    "Для тех, кто уже освоил основы и хочет двигаться дальше: усложнённые " +
    "связки, работа с партнёром по классу, более быстрый темп.",
  individual:
    "Персональный разбор техники и подготовка к выступлению в удобное " +
    "время, в своём темпе.",
};

export async function getDirections(): Promise<Direction[]> {
  const classes = await getClasses();
  return classes.map((item) => ({
    key: item.key,
    label: item.label,
    description: DESCRIPTIONS[item.key] ?? "",
  }));
}
