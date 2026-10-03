import type { Metadata } from "next";
import { getMyBookings, type UserBooking } from "@/lib/account";
import { cancelBookingAction } from "@/lib/actions";
import { formatClassDateTime } from "@/lib/format";
import { ConfirmSubmitButton } from "@/components/ConfirmSubmitButton";

export const metadata: Metadata = {
  title: "Мои занятия",
};

// Баланс и статус записи меняются в реальном времени — не кэшируем статически.
export const dynamic = "force-dynamic";

type SearchParams = Promise<{
  cancelled?: string;
  cancel_error?: string;
}>;

export default async function AccountBookingsPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const { cancelled, cancel_error: cancelError } = await searchParams;
  const bookings = await getMyBookings();
  const { upcoming, past } = splitByTime(bookings);

  return (
    <div className="flex flex-col gap-8">
      {cancelled && (
        <p className="rounded-md bg-[var(--success-bg)] p-3 text-sm text-[var(--success-text)]">
          Запись отменена, занятие возвращено на баланс.
        </p>
      )}
      {cancelError && (
        <p className="rounded-md bg-[var(--danger-bg)] p-3 text-sm text-[var(--danger-text)]">
          {cancelError}
        </p>
      )}

      <section>
        <h2 className="mb-4 text-xl font-semibold">Предстоящие</h2>
        {upcoming.length === 0 ? (
          <p className="text-[var(--text-secondary)]">
            Пока нет предстоящих занятий. Запишитесь в расписании.
          </p>
        ) : (
          <BookingList bookings={upcoming} allowCancel />
        )}
      </section>

      <section>
        <h2 className="mb-4 text-xl font-semibold">Прошедшие</h2>
        {past.length === 0 ? (
          <p className="text-[var(--text-secondary)]">Пока нет истории занятий.</p>
        ) : (
          <BookingList bookings={past} allowCancel={false} />
        )}
      </section>
    </div>
  );
}

// Отдельная обычная функция, а не логика прямо в теле компонента: вызов
// Date.now() внутри функции компонента помечается линтером как нечистый.
function splitByTime(bookings: UserBooking[]) {
  const now = Date.now();
  return {
    upcoming: bookings.filter(
      (booking) => new Date(booking.starts_at).getTime() >= now,
    ),
    past: bookings.filter(
      (booking) => new Date(booking.starts_at).getTime() < now,
    ),
  };
}

function BookingList({
  bookings,
  allowCancel,
}: {
  bookings: UserBooking[];
  allowCancel: boolean;
}) {
  return (
    <ul className="flex flex-col gap-3">
      {bookings.map((booking) => (
        <li
          key={booking.id}
          className="flex flex-wrap items-baseline justify-between gap-2 rounded-2xl glass-medium p-4"
        >
          <span className="font-medium">{booking.class_label}</span>
          <span className="text-sm text-[var(--text-secondary)]">
            {formatClassDateTime(booking.starts_at)}
          </span>
          {booking.booking_status === "cancelled" ? (
            <span className="text-sm text-[var(--text-secondary)]">Отменено</span>
          ) : booking.slot_status !== "open" ? (
            <span className="text-sm text-[var(--text-secondary)]">
              Занятие отменено студией
            </span>
          ) : (
            allowCancel && (
              <form action={cancelBookingAction}>
                <input type="hidden" name="slot_id" value={booking.slot_id} />
                <ConfirmSubmitButton
                  confirmMessage="Отменить запись? Занятие вернётся на баланс."
                  className="text-sm font-medium text-[var(--danger)] hover:underline"
                >
                  Отменить запись
                </ConfirmSubmitButton>
              </form>
            )
          )}
        </li>
      ))}
    </ul>
  );
}
