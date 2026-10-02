"use client";

import { useEffect, useId, useState } from "react";
import { useRouter } from "next/navigation";

/**
 * Поля, которые Telegram Login Widget передаёт в колбэк после входа.
 * Совпадает с `TelegramAuthRequest` на backend
 * (`src/flamenco_bot/api/schemas.py`) — подпись (`hash`) проверяется там,
 * фронтенд ей не доверяет и ничего сам не проверяет.
 */
type TelegramWidgetUser = {
  id: number;
  first_name?: string;
  last_name?: string;
  username?: string;
  photo_url?: string;
  auth_date: number;
  hash: string;
};

type TelegramAuthCallback = (user: TelegramWidgetUser) => void;

// Виджет вызывает колбэк по имени из глобальной области (`window`), а не
// через проп/событие React — так работает его встраиваемый скрипт.
// Индексация через `Record` вместо расширения `interface Window`, чтобы не
// заявлять произвольные строковые свойства глобально для всего приложения.
function getWindowCallbacks(): Record<string, TelegramAuthCallback | undefined> {
  return window as unknown as Record<string, TelegramAuthCallback | undefined>;
}

const BOT_USERNAME = process.env.NEXT_PUBLIC_TELEGRAM_BOT_USERNAME;

export function TelegramLoginWidget() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  // Отдельное имя колбэка на каждый экземпляр виджета — на случай, если
  // страница когда-нибудь отрендерит его дважды.
  const reactId = useId().replace(/[^a-zA-Z0-9]/g, "");
  const callbackName = `onTelegramAuth_${reactId}`;

  useEffect(() => {
    getWindowCallbacks()[callbackName] = async (user: TelegramWidgetUser) => {
      setError(null);
      setPending(true);
      try {
        const response = await fetch("/api/auth/telegram", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(user),
        });
        if (!response.ok) {
          setError(
            response.status === 401
              ? "Не удалось подтвердить вход через Telegram. Попробуйте ещё раз."
              : "Что-то пошло не так. Попробуйте ещё раз позже.",
          );
          setPending(false);
          return;
        }
        router.push("/");
        router.refresh();
      } catch {
        setError("Не удалось связаться с сервером. Проверьте соединение.");
        setPending(false);
      }
    };

    const container = document.getElementById(`telegram-login-${reactId}`);
    if (container && BOT_USERNAME) {
      const script = document.createElement("script");
      script.src = "https://telegram.org/js/telegram-widget.js?22";
      script.async = true;
      script.setAttribute("data-telegram-login", BOT_USERNAME);
      script.setAttribute("data-size", "large");
      script.setAttribute("data-onauth", `${callbackName}(user)`);
      script.setAttribute("data-request-access", "write");
      container.appendChild(script);
    }

    return () => {
      delete getWindowCallbacks()[callbackName];
    };
  }, [callbackName, reactId, router]);

  if (!BOT_USERNAME) {
    return (
      <p className="text-sm text-[var(--text-secondary)]">
        Вход через Telegram не настроен: не задан
        NEXT_PUBLIC_TELEGRAM_BOT_USERNAME.
      </p>
    );
  }

  return (
    <div className="flex flex-col items-center gap-3">
      <div id={`telegram-login-${reactId}`} />
      {pending && (
        <p className="text-sm text-[var(--text-secondary)]">Входим…</p>
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  );
}
