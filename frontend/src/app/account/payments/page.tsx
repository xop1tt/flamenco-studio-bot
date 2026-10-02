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
          <p className="text-[var(--foreground)]/70">
            Платежей пока нет. Выбрать абонемент можно на{" "}
            <Link href="/packages" className="text-[var(--accent)] hover:underline">
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
          className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-black/10 p-4"
        >
          <div className="flex flex-col gap-1">
            <span className="font-medium">{payment.package_title}</span>
            <span className="text-sm text-[var(--foreground)]/60">
              {formatClassDateTime(payment.created_at)} ·{" "}
              {Math.round(payment.amount_minor / 100)} ₽
            </span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium text-[var(--foreground)]/80">
              {STATUS_LABELS[payment.status] ?? payment.status}
            </span>
            {payment.status === "pending" && (
              <form action={checkPaymentAction}>
                <input type="hidden" name="payment_id" value={payment.id} />
                <button
                  type="submit"
                  className="rounded-md border border-black/15 px-3 py-1.5 text-sm font-medium transition hover:border-[var(--accent)] hover:text-[var(--accent)]"
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
