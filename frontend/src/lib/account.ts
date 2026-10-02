import { cookies } from "next/headers";

/**
 * Личный кабинет (Stage 5): профиль, баланс, мои занятия, поддержка.
 * Все данные — с backend (`src/flamenco_bot/api`), сессия передаётся тем же
 * способом, что и в `lib/auth.ts`: cookie пересылается напрямую backend'у,
 * а не через rewrite (это серверные компоненты, не браузер).
 */

const API_BASE_URL = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";
const SESSION_COOKIE_NAME = "session";

async function fetchWithSession<T>(path: string): Promise<T | null> {
  const cookieStore = await cookies();
  const session = cookieStore.get(SESSION_COOKIE_NAME);
  if (!session) {
    return null;
  }
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { cookie: `${SESSION_COOKIE_NAME}=${session.value}` },
      cache: "no-store",
    });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as T;
  } catch (error) {
    console.error(`Account API request failed: ${path}`, error);
    return null;
  }
}

export type Profile = {
  telegram_id: number;
  user_name: string;
  phone: string | null;
  lesson_credits: number;
  registered_at: string;
  is_admin: boolean;
};

export type UserBooking = {
  id: number;
  slot_id: number;
  class_key: string;
  class_label: string;
  starts_at: string;
  booking_status: string;
  slot_status: string;
};

export type SupportTicket = {
  id: number;
  status: string;
  created_at: string;
  updated_at: string;
  last_message: string;
};

export type PaymentHistoryItem = {
  id: number;
  package_key: string;
  package_title: string;
  lessons: number;
  amount_minor: number;
  status: string;
  created_at: string;
};

export async function getProfile(): Promise<Profile | null> {
  return fetchWithSession<Profile>("/api/users/me/profile");
}

export async function getMyBookings(): Promise<UserBooking[]> {
  return (await fetchWithSession<UserBooking[]>("/api/bookings/me")) ?? [];
}

export async function getMySupportTickets(): Promise<SupportTicket[]> {
  return (await fetchWithSession<SupportTicket[]>("/api/support/me")) ?? [];
}

export async function getMyPayments(): Promise<PaymentHistoryItem[]> {
  return (await fetchWithSession<PaymentHistoryItem[]>("/api/payments/me")) ?? [];
}
