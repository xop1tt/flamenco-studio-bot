import type { Metadata } from "next";
import { CONTACTS } from "@/lib/contacts";

export const metadata: Metadata = {
  title: "Контакты",
};

// Telegram-бот — не плейсхолдер, username уже настроен в окружении (тот же,
// что используется в hero на главной и для входа).
const TELEGRAM_BOT_USERNAME = process.env.NEXT_PUBLIC_TELEGRAM_BOT_USERNAME;

export default function ContactPage() {
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 px-4 py-12 sm:py-16">
      <div className="flex flex-col gap-3">
        <span className="eyebrow">Mirada Studio</span>
        <h1 className="font-heading text-4xl font-bold tracking-tight sm:text-5xl">Контакты</h1>
      </div>
      <p className="text-lg leading-relaxed text-[var(--text-secondary)]">
        Свяжитесь со студией любым удобным способом — поможем выбрать
        направление и время занятия.
      </p>
      {TELEGRAM_BOT_USERNAME && (
        <a
          href={`https://t.me/${TELEGRAM_BOT_USERNAME}`}
          target="_blank"
          rel="noopener noreferrer"
          className="btn-primary w-fit gap-2 rounded-full px-6 py-3 text-base font-semibold"
        >
          Написать в Telegram
        </a>
      )}
      <dl className="flex flex-col gap-4 rounded-[28px] glass-medium p-7">
        <ContactRow label="Адрес" value={CONTACTS.address} />
        <ContactRow label="Телефон" value={CONTACTS.phone} />
        <ContactRow
          label="Telegram"
          value={TELEGRAM_BOT_USERNAME ? `@${TELEGRAM_BOT_USERNAME}` : "Ссылка на Telegram-бота уточняется"}
        />
        <ContactRow label="Email" value={CONTACTS.email} />
      </dl>

      {/* Плейсхолдер: имя преподавателя, фото зала и отзывы — реальный контент
          студии, его нельзя выдумывать. Заполнить перед запуском. */}
      <div className="rounded-[28px] glass-medium p-7">
        <h2 className="font-heading mb-2 text-xl font-bold tracking-tight">
          Как проходит первое занятие
        </h2>
        <p className="text-base leading-relaxed text-[var(--text-secondary)]">
          Приходите за 10–15 минут до начала — познакомимся, расскажем про
          группу и формат занятия, поможем с первыми движениями. Никакой
          специальной подготовки не нужно.
        </p>
        <p className="mt-3 text-sm text-[var(--text-secondary)]">
          Преподаватель и фото зала — уточняются.
        </p>
      </div>
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
