import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/auth";
import { TelegramLoginWidget } from "@/components/TelegramLoginWidget";

export const metadata: Metadata = {
  title: "Вход",
};

// Сессия читается из cookie на каждый запрос — страницу нельзя кэшировать.
export const dynamic = "force-dynamic";

export default async function LoginPage() {
  const currentUser = await getCurrentUser();
  if (currentUser) {
    redirect("/");
  }

  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-6 px-4 py-16 text-center">
      <h1 className="text-3xl font-semibold">Вход</h1>
      <p className="text-base leading-relaxed text-[var(--text-secondary)]">
        Войдите через Telegram — это тот же аккаунт, что в боте студии.
      </p>
      <div className="w-full rounded-2xl glass-medium p-6">
        <TelegramLoginWidget />
      </div>
    </div>
  );
}
