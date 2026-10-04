import type { Metadata } from "next";
import { getMySupportTickets } from "@/lib/account";
import { submitSupportMessageAction } from "@/lib/actions";
import { formatClassDateTime } from "@/lib/format";

export const metadata: Metadata = {
  title: "Помощь",
};

const ERROR_MESSAGES: Record<string, string> = {
  empty: "Сообщение должно содержать хотя бы один символ.",
  rate_limited:
    "Слишком много сообщений подряд. Попробуйте через несколько минут.",
  network: "Не удалось связаться с сервером. Попробуйте ещё раз.",
  failed: "Что-то пошло не так. Попробуйте ещё раз позже.",
};

type SearchParams = Promise<{ error?: string; submitted?: string }>;

export default async function AccountSupportPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const { error, submitted } = await searchParams;
  const tickets = await getMySupportTickets();

  return (
    <div className="flex flex-col gap-8">
      <section className="rounded-2xl glass-medium p-6">
        <h2 className="mb-1 text-xl font-semibold">Помощь</h2>
        <p className="mb-4 text-sm text-[var(--text-secondary)]">
          Напишите вопрос — его получат администраторы студии. Ответ придёт в
          Telegram-бот студии и появится в списке ниже.
        </p>
        {submitted && (
          <p className="mb-4 rounded-md bg-[var(--success-bg)] p-3 text-sm text-[var(--success-text)]">
            Сообщение отправлено. Ответ придёт в Telegram-бот студии и
            появится в списке ниже.
          </p>
        )}
        {error && (
          <p className="mb-4 rounded-md bg-[var(--danger-bg)] p-3 text-sm text-[var(--danger-text)]">
            {ERROR_MESSAGES[error] ?? ERROR_MESSAGES.failed}
          </p>
        )}
        <form action={submitSupportMessageAction} className="flex flex-col gap-3">
          <label htmlFor="support-body" className="sr-only">
            Текст обращения
          </label>
          <textarea
            id="support-body"
            name="body"
            required
            maxLength={2000}
            rows={4}
            placeholder="Ваш вопрос…"
            className="rounded-xl border border-[var(--border-strong)] bg-[var(--surface)] p-3 text-base focus:border-[var(--primary)] focus:outline-none"
          />
          <button
            type="submit"
            className="btn-primary self-start rounded-full px-6 py-2.5 font-medium"
          >
            Отправить
          </button>
        </form>
      </section>

      <section>
        <h2 className="mb-4 text-xl font-semibold">Мои обращения</h2>
        {tickets.length === 0 ? (
          <p className="text-[var(--text-secondary)]">Обращений пока нет.</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {tickets.map((ticket) => (
              <li
                key={ticket.id}
                className="flex flex-col gap-1 rounded-2xl glass-medium p-4"
              >
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="font-medium">Обращение №{ticket.id}</span>
                  <span className="text-sm text-[var(--text-secondary)]">
                    {ticket.status === "open" ? "Открыто" : "Закрыто"} ·{" "}
                    {formatClassDateTime(ticket.updated_at)}
                  </span>
                </div>
                {ticket.last_message && (
                  <p className="text-sm text-[var(--text-secondary)]">
                    {ticket.last_message}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
