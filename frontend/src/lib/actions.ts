"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";
const SESSION_COOKIE_NAME = "session";

export async function logoutAction(): Promise<void> {
  const cookieStore = await cookies();
  const session = cookieStore.get(SESSION_COOKIE_NAME);
  if (session) {
    try {
      // Сессия — stateless JWT (backend ничего не хранит про неё сам по
      // себе), так что вызов backend не обязателен для выхода на этом
      // устройстве, но сохраняет один источник правды на случай, если
      // backend когда-нибудь добавит отзыв сессий на своей стороне.
      await fetch(`${API_BASE_URL}/api/auth/logout`, {
        method: "POST",
        headers: { cookie: `${SESSION_COOKIE_NAME}=${session.value}` },
      });
    } catch (error) {
      console.error("Logout request to backend failed", error);
    }
  }
  cookieStore.delete(SESSION_COOKIE_NAME);
  redirect("/");
}
