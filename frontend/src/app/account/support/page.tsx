import type { Metadata } from "next";
import { getMySupportTickets } from "@/lib/account";
import { submitSupportMessageAction } from "@/lib/actions";
import { formatClassDateTime } from "@/lib/format";

export const metadata: Metadata = {
  title: "Поддержка",
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
      <section className="rounded-2xl border border-[var(--border-strong)] bg-[var(--surface)] p-6 shadow-[var(--shadow-card)]">
        <h2 className="mb-4 text-xl font-semibold">Новое обращение</h2>
        {submitted && (
          <p className="mb-4 rounded-md bg-green-50 p-3 text-sm text-green-800">
            Обращение отправлено. Администратор ответит здесь же.
          </p>
        )}
        {error && (
          <p className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-800">
            {ERROR_MESSAGES[error] ?? ERROR_MESSAGES.failed}
          </p>
        )}
        <form action={submitSupportMessageAction} className="flex flex-col gap-3">
          <textarea
            name="body"
            required
            maxLength={2000}
            rows={4}
            placeholder="Опишите вопрос..."
            className="rounded-xl border border-[var(--border-strong)] bg-[var(--surface)] p-3 text-base focus:border-[var(--primary)] focus:outline-none"
          />
          <button
            type="submit"
            className="self-start rounded-full bg-[var(--primary)] px-6 py-2.5 font-medium text-[var(--surface)] shadow-[var(--shadow-card)] transition hover:bg-[var(--primary-hover)] hover:shadow-[var(--shadow-card-hover)]"
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
                className="flex flex-col gap-1 rounded-2xl border border-[var(--border-strong)] bg-[var(--surface)] p-4 shadow-[var(--shadow-card)]"
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
