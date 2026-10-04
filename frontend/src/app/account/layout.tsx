import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/auth";
import { AccountNav } from "@/components/AccountNav";

const TELEGRAM_BOT_USERNAME = process.env.NEXT_PUBLIC_TELEGRAM_BOT_USERNAME;

// Личный кабинет не имеет смысла без сессии — читаем cookie на каждый
// запрос, поэтому не кэшируем.
export const dynamic = "force-dynamic";

export default async function AccountLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const currentUser = await getCurrentUser();
  if (!currentUser) {
    redirect("/login");
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-12">
      <div className="flex flex-col gap-2">
        <h1 className="text-3xl font-semibold">Личный кабинет</h1>
        <p className="text-sm text-[var(--text-secondary)]">
          Тот же аккаунт, что в Telegram-боте студии
          {TELEGRAM_BOT_USERNAME ? (
            <>
              {" "}
              <a
                href={`https://t.me/${TELEGRAM_BOT_USERNAME}`}
                target="_blank"
                rel="noopener noreferrer"
                className="font-medium text-[var(--primary)] underline-offset-4 hover:underline"
              >
                @{TELEGRAM_BOT_USERNAME}
              </a>
            </>
          ) : null}
          : записи, баланс и обращения общие.
        </p>
      </div>
      <AccountNav />
      {currentUser.telegram_id === null ? (
        <p className="rounded-2xl glass-medium p-6 text-base leading-relaxed text-[var(--text-secondary)]">
          Привяжите Telegram к аккаунту, чтобы видеть профиль, баланс занятий
          и записи — на сайте пока нет формы для этого, напишите в «💬 Помощь»
          в Telegram-боте студии.
        </p>
      ) : (
        children
      )}
    </div>
  );
}
