import { cookies } from "next/headers";

/**
 * Авторизация пользователя сайта (`/api/auth/*` на backend — см.
 * `src/flamenco_bot/api/routers/auth.py`). Сессия — httponly JWT-cookie
 * `session`, которую подписывает backend; фронтенд её не парсит и не
 * проверяет сам, только пересылает backend'у и спрашивает "кто я".
 */

const API_BASE_URL = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";
const SESSION_COOKIE_NAME = "session";

export type CurrentUser = {
  id: number;
  email: string | null;
  telegram_id: number | null;
  display_name: string;
  created_at: string;
};

/**
 * Читает текущего пользователя на сервере (Server Component), пересылая
 * cookie сессии бэкенду напрямую (не через rewrite в next.config.ts — тот
 * нужен для запросов из браузера, а не сервер-сервер).
 */
export async function getCurrentUser(): Promise<CurrentUser | null> {
  const cookieStore = await cookies();
  const session = cookieStore.get(SESSION_COOKIE_NAME);
  if (!session) {
    return null;
  }
  try {
    const response = await fetch(`${API_BASE_URL}/api/auth/me`, {
      headers: { cookie: `${SESSION_COOKIE_NAME}=${session.value}` },
      cache: "no-store",
    });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as CurrentUser;
  } catch (error) {
    console.error("Failed to load current user", error);
    return null;
  }
}
