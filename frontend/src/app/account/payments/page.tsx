import type { Metadata } from "next";
import Link from "next/link";
import { getMyPayments, type PaymentHistoryItem } from "@/lib/account";
import { checkPaymentAction } from "@/lib/actions";
import { formatClassDateTime } from "@/lib/format";

export const metadata: Metadata = {
  title: "Платежи",
};

const STATUS_LABELS: Record<string, string> = {
  pending: "Ожидает оплаты",
  succeeded: "Оплачено",
  canceled: "Отменён",
  refund_pending: "Возврат в обработке",
  refunded: "Возвращён",
};

type SearchParams = Promise<{ checkout_error?: string }>;

export default async function AccountPaymentsPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const { checkout_error: checkoutError } = await searchParams;
  const payments = await getMyPayments();

  return (
    <div className="flex flex-col gap-6">
      {checkoutError && (
        <p className="rounded-md bg-red-50 p-3 text-sm text-red-800">
          {checkoutError === "no_confirmation_url"
            ? "Платёж создан, но ссылка на оплату недоступна. Проверьте статус ниже чуть позже."
            : checkoutError}
        </p>
      )}

      <section>
        <h2 className="mb-4 text-xl font-semibold">История платежей</h2>
        {payments.length === 0 ? (
          <p className="text-[var(--text-secondary)]">
            Платежей пока нет. Выбрать абонемент можно на{" "}
            <Link href="/packages" className="text-[var(--primary)] hover:underline">
              странице абонементов
            </Link>
            .
          </p>
        ) : (
          <PaymentList payments={payments} />
        )}
      </section>
    </div>
  );
}

function PaymentList({ payments }: { payments: PaymentHistoryItem[] }) {
  return (
    <ul className="flex flex-col gap-3">
      {payments.map((payment) => (
        <li
          key={payment.id}
          className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-[var(--border-strong)] bg-[var(--surface)] p-4 shadow-[var(--shadow-card)]"
        >
          <div className="flex flex-col gap-1">
            <span className="font-medium">{payment.package_title}</span>
            <span className="text-sm text-[var(--text-secondary)]">
              {formatClassDateTime(payment.created_at)} ·{" "}
              {Math.round(payment.amount_minor / 100)} ₽
            </span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium text-[var(--text-secondary)]">
              {STATUS_LABELS[payment.status] ?? payment.status}
            </span>
            {payment.status === "pending" && (
              <form action={checkPaymentAction}>
                <input type="hidden" name="payment_id" value={payment.id} />
                <button
                  type="submit"
                  className="rounded-full border border-[var(--border-strong)] bg-[var(--surface)] px-4 py-1.5 text-sm font-medium transition hover:border-[var(--primary)] hover:text-[var(--primary)]"
                >
                  Проверить оплату
                </button>
              </form>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}
