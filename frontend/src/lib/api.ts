/**
 * Тонкий клиент к backend API (`src/flamenco_bot/api`).
 *
 * Запросы выполняются на сервере Next.js (в серверных компонентах), а не в
 * браузере — так фронтенд не дублирует бизнес-логику и не требует CORS на
 * backend. `API_BASE_URL` — серверная переменная окружения (без
 * `NEXT_PUBLIC_`), в браузер никогда не попадает.
 */

const API_BASE_URL = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

export type ClassSlot = {
  id: number;
  class_key: string;
  class_label: string;
  starts_at: string;
  capacity: number;
  remaining: number;
  status: string;
};

export type LessonPackage = {
  key: string;
  title: string;
  lessons: number;
  price_rub: number;
};

export type ClassFormat = {
  key: string;
  label: string;
  description: string;
  level: string;
};

async function apiFetch<T>(path: string): Promise<T | null> {
  try {
    const response = await fetch(`${API_BASE_URL}${path}`);
    if (!response.ok) {
      console.error(`API request failed: ${path} -> ${response.status}`);
      return null;
    }
    return (await response.json()) as T;
  } catch (error) {
    console.error(`API request errored: ${path}`, error);
    return null;
  }
}

export async function getSchedule(classKey?: string): Promise<ClassSlot[]> {
  const query = classKey ? `?class_key=${encodeURIComponent(classKey)}` : "";
  return (await apiFetch<ClassSlot[]>(`/api/schedule${query}`)) ?? [];
}

export async function getPackages(): Promise<LessonPackage[]> {
  return (await apiFetch<LessonPackage[]>("/api/packages")) ?? [];
}

export async function getClasses(): Promise<ClassFormat[]> {
  return (await apiFetch<ClassFormat[]>("/api/classes")) ?? [];
}

// Правила записи — из backend (те же константы, по которым их проверяет
// репозиторий). Значения по умолчанию — на случай недоступного API: это
// только подписи, окончательную проверку всё равно делает backend.
export type BookingRules = {
  cancellation_deadline_hours: number;
  rebook_cooldown_hours: number;
};

const DEFAULT_BOOKING_RULES: BookingRules = {
  cancellation_deadline_hours: 24,
  rebook_cooldown_hours: 12,
};

export async function getBookingRules(): Promise<BookingRules> {
  return (
    (await apiFetch<BookingRules>("/api/bookings/rules")) ?? DEFAULT_BOOKING_RULES
  );
}

/** Записаться можно только на открытое занятие со свободными местами. */
export function isBookable(slot: ClassSlot): boolean {
  return slot.status === "open" && slot.remaining > 0;
}
