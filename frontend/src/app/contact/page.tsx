import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Контакты",
};

// Плейсхолдеры: в репозитории нет реальных контактных данных студии
// (адрес/телефон/соцсети/ссылка на Telegram-бота). Замените на настоящие
// значения перед запуском сайта.
const CONTACTS = {
  address: "Адрес уточняется",
  phone: "Телефон уточняется",
  telegram: "Ссылка на Telegram-бота уточняется",
  email: "Email уточняется",
};

export default function ContactPage() {
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 px-4 py-12">
      <h1 className="text-3xl font-bold">Контакты</h1>
      <p className="text-[var(--text-secondary)]">
        Свяжитесь со студией любым удобным способом — поможем выбрать
        направление и время занятия.
      </p>
      <dl className="flex flex-col gap-4 rounded-lg border border-[var(--border-strong)] bg-[var(--surface)] p-6 shadow-sm">
        <ContactRow label="Адрес" value={CONTACTS.address} />
        <ContactRow label="Телефон" value={CONTACTS.phone} />
        <ContactRow label="Telegram" value={CONTACTS.telegram} />
        <ContactRow label="Email" value={CONTACTS.email} />
      </dl>
    </div>
  );
}

function ContactRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1 sm:flex-row sm:gap-3">
      <dt className="w-28 shrink-0 font-medium">{label}</dt>
      <dd className="text-[var(--text-secondary)]">{value}</dd>
    </div>
  );
}
