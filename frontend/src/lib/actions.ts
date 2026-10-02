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

export async function submitSupportMessageAction(
  formData: FormData,
): Promise<void> {
  const cookieStore = await cookies();
  const session = cookieStore.get(SESSION_COOKIE_NAME);
  if (!session) {
    redirect("/login");
  }

  const body = String(formData.get("body") ?? "").trim();
  if (!body) {
    redirect("/account/support?error=empty");
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/support`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        cookie: `${SESSION_COOKIE_NAME}=${session.value}`,
      },
      body: JSON.stringify({ body }),
    });
  } catch (error) {
    console.error("Support submission request failed", error);
    redirect("/account/support?error=network");
  }

  if (!response.ok) {
    const reason = response.status === 429 ? "rate_limited" : "failed";
    redirect(`/account/support?error=${reason}`);
  }

  redirect("/account/support?submitted=1");
}

function scheduleRedirectUrl(
  classKey: string | null,
  params: Record<string, string>,
): string {
  const search = new URLSearchParams();
  if (classKey) {
    search.set("class_key", classKey);
  }
  for (const [key, value] of Object.entries(params)) {
    search.set(key, value);
  }
  const query = search.toString();
  return query ? `/schedule?${query}` : "/schedule";
}

export async function bookClassAction(formData: FormData): Promise<void> {
  const slotId = Number(formData.get("slot_id"));
  const classKey = (formData.get("class_key") as string | null) || null;

  const cookieStore = await cookies();
  const session = cookieStore.get(SESSION_COOKIE_NAME);
  if (!session) {
    redirect("/login");
  }
  if (!Number.isFinite(slotId) || slotId <= 0) {
    redirect(scheduleRedirectUrl(classKey, { book_error: "Некорректная запись" }));
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/bookings`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        cookie: `${SESSION_COOKIE_NAME}=${session.value}`,
      },
      body: JSON.stringify({ slot_id: slotId }),
    });
  } catch (error) {
    console.error("Booking request failed", error);
    redirect(
      scheduleRedirectUrl(classKey, {
        book_error: "Не удалось связаться с сервером. Попробуйте ещё раз.",
      }),
    );
  }

  if (response.status === 401) {
    redirect("/login");
  }

  if (!response.ok) {
    // Backend уже формулирует понятные причины (слот занят/закрыт, не
    // привязан Telegram и т.д.) — переиспользуем их вместо своего перевода.
    let detail = "Не удалось записаться. Попробуйте ещё раз позже.";
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) {
        detail = body.detail;
      }
    } catch {
      // используем сообщение по умолчанию
    }
    redirect(scheduleRedirectUrl(classKey, { book_error: detail }));
  }

  const booking = (await response.json()) as { already_booked: boolean };
  redirect(
    scheduleRedirectUrl(classKey, {
      booked: String(slotId),
      already: booking.already_booked ? "1" : "0",
    }),
  );
}
