import type { Metadata } from "next";
import { getProfile } from "@/lib/account";
import Link from "next/link";
import { lessonsCount } from "@/lib/format";
import { GLASS_BUTTON_CLASS, PRIMARY_BUTTON_CLASS } from "@/lib/glass";

export const metadata: Metadata = {
  title: "Профиль",
};

export default async function AccountProfilePage() {
  const profile = await getProfile();

  if (!profile) {
    return (
      <p className="text-[var(--text-secondary)]">
        Не удалось загрузить профиль. Попробуйте обновить страницу позже.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <section className="rounded-2xl glass-medium p-6">
        <h2 className="mb-4 text-xl font-semibold">Профиль</h2>
        <dl className="flex flex-col gap-3">
          <Row label="Имя" value={profile.user_name} />
          <Row label="Телефон" value={profile.phone ?? "не указан"} />
        </dl>
        <p className="mt-4 text-sm text-[var(--text-secondary)]">
          Имя и телефон меняются в Telegram-боте студии: «👤 Профиль».
        </p>
      </section>

      <section className="flex flex-wrap items-center justify-between gap-4 rounded-2xl glass-medium p-6">
        <div>
          <h2 className="mb-1 text-xl font-semibold">Баланс</h2>
          <p className="text-2xl font-bold text-[var(--primary)]">
            {lessonsCount(profile.lesson_credits)}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link href="/schedule" className={`${PRIMARY_BUTTON_CLASS} px-5 py-2 text-sm`}>
            Записаться
          </Link>
          <Link href="/packages" className={`${GLASS_BUTTON_CLASS} px-5 py-2 text-sm`}>
            Абонементы
          </Link>
        </div>
      </section>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1 sm:flex-row sm:gap-3">
      <dt className="w-40 shrink-0 font-medium">{label}</dt>
      <dd className="text-[var(--text-secondary)]">{value}</dd>
    </div>
  );
}
