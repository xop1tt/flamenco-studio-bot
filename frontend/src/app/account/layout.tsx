import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/auth";
import { AccountNav } from "@/components/AccountNav";

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
      <h1 className="text-3xl font-bold">Личный кабинет</h1>
      <AccountNav />
      {currentUser.telegram_id === null ? (
        <p className="rounded-lg border border-[var(--border-strong)] bg-[var(--surface)] p-6 text-[var(--text-secondary)] shadow-sm">
          Привяжите Telegram к аккаунту, чтобы видеть профиль, баланс занятий
          и записи — на сайте пока нет формы для этого, напишите в поддержку
          через бота.
        </p>
      ) : (
        children
      )}
    </div>
  );
}
