import type { Metadata } from "next";
import { getProfile } from "@/lib/account";
import { formatClassDateTime } from "@/lib/format";

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
      <section className="rounded-2xl glass-card p-6 shadow-[var(--shadow-card)]">
        <h2 className="mb-4 text-xl font-semibold">Профиль</h2>
        <dl className="flex flex-col gap-3">
          <Row label="Имя" value={profile.user_name} />
          <Row label="Телефон" value={profile.phone ?? "не указан"} />
          <Row label="Telegram ID" value={String(profile.telegram_id)} />
          <Row
            label="Дата регистрации"
            value={formatClassDateTime(profile.registered_at)}
          />
          {profile.is_admin && <Row label="Статус" value="Администратор" />}
        </dl>
      </section>

      <section className="rounded-2xl glass-card p-6 shadow-[var(--shadow-card)]">
        <h2 className="mb-2 text-xl font-semibold">Баланс</h2>
        <p className="text-3xl font-bold text-[var(--primary)]">
          {profile.lesson_credits}
        </p>
        <p className="text-sm text-[var(--text-secondary)]">
          {profile.lesson_credits === 1
            ? "занятие осталось"
            : "занятий осталось"}
        </p>
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
