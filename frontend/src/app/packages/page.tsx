import type { Metadata } from "next";
import { getPackages } from "@/lib/api";
import { getCurrentUser } from "@/lib/auth";
import { PackagesGrid } from "@/components/PackagesGrid";

export const metadata: Metadata = {
  title: "Абонементы",
};

// Цены и состав абонементов задаёт backend — не кэшируем статически на
// этапе сборки, иначе сайт будет показывать устаревший каталог.
export const dynamic = "force-dynamic";

type SearchParams = Promise<{ checkout_error?: string }>;

export default async function PackagesPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const { checkout_error: checkoutError } = await searchParams;
  const [packages, currentUser] = await Promise.all([
    getPackages(),
    getCurrentUser(),
  ]);

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 px-4 py-12">
      <h1 className="text-3xl font-semibold">Абонементы</h1>
      <p className="max-w-2xl text-[var(--text-secondary)]">
        Разовое занятие или абонемент на несколько занятий — цены и состав
        всегда актуальны, их определяет студия.
      </p>
      {checkoutError && (
        <p className="rounded-md bg-red-50 p-3 text-sm text-red-800">
          {checkoutError}
        </p>
      )}
      {!currentUser && (
        <p className="text-sm text-[var(--text-secondary)]">
          Вход через Telegram нужен, чтобы абонемент и записи сохранялись в
          вашем профиле — это тот же аккаунт, что в боте студии, входить
          заново для каждой записи не придётся.
        </p>
      )}
      <PackagesGrid packages={packages} isAuthenticated={currentUser !== null} />
    </div>
  );
}
