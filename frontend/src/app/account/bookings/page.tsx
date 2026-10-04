import type { Metadata } from "next";
import Link from "next/link";
import { getMyBookings, getProfile, type UserBooking } from "@/lib/account";
import { getBookingRules } from "@/lib/api";
import { cancelBookingAction } from "@/lib/actions";
import { balanceLabel, formatClassDateTime, hoursLabel } from "@/lib/format";
import { GLASS_BUTTON_CLASS, PRIMARY_BUTTON_CLASS } from "@/lib/glass";
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

// Те же правила, что в «Мои занятия» Telegram-бота: предстоящие — от
// ближайшего, отмена — только пока она разрешена (срок приходит с backend),
// с подтверждением; баланс — рядом со списком.
export default async function AccountBookingsPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const { cancelled, cancel_error: cancelError } = await searchParams;
  const [bookings, profile, rules] = await Promise.all([
    getMyBookings(),
    getProfile(),
    getBookingRules(),
  ]);
  const { upcoming, history, now } = splitBookings(bookings);
  const balance = profile ? balanceLabel(profile.lesson_credits) : null;

  return (
    <div className="flex flex-col gap-8">
      {cancelled && (
        <p className="rounded-md bg-[var(--success-bg)] p-3 text-sm text-[var(--success-text)]">
          Запись отменена. Занятие вернулось на баланс
          {balance ? ` — ${balance}` : ""}.
        </p>
      )}
      {cancelError && (
        <p className="rounded-md bg-[var(--danger-bg)] p-3 text-sm text-[var(--danger-text)]">
          {cancelError}
        </p>
      )}

      <section className="flex flex-col gap-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-xl font-semibold">Предстоящие</h2>
          {balance && (
            <span className="text-sm font-medium text-[var(--primary)]">{balance}</span>
          )}
        </div>
        {upcoming.length === 0 ? (
          <div className="flex flex-col items-start gap-3">
            <p className="text-[var(--text-secondary)]">
              Предстоящих занятий пока нет.
            </p>
            <div className="flex flex-wrap gap-2">
              <Link
                href="/schedule"
                className={`${PRIMARY_BUTTON_CLASS} px-5 py-2 text-sm`}
              >
                Записаться
              </Link>
              <Link
                href="/packages"
                className={`${GLASS_BUTTON_CLASS} px-5 py-2 text-sm`}
              >
                Абонементы
              </Link>
            </div>
          </div>
        ) : (
          <>
            <ul className="flex flex-col gap-3">
              {upcoming.map((booking) => (
                <UpcomingBooking
                  key={booking.id}
                  booking={booking}
                  canCancel={new Date(booking.cancellable_until).getTime() > now}
                  rebookCooldownHours={rules.rebook_cooldown_hours}
                />
              ))}
            </ul>
            <p className="text-sm text-[var(--text-secondary)]">
              Отменить запись можно не позднее чем за{" "}
              {hoursLabel(rules.cancellation_deadline_hours)} до начала — занятие
              вернётся на баланс.
            </p>
          </>
        )}
      </section>

      <section>
        <h2 className="mb-4 text-xl font-semibold">История</h2>
        {history.length === 0 ? (
          <p className="text-[var(--text-secondary)]">Пока нет истории занятий.</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {history.map((booking) => (
              <li
                key={booking.id}
                className="flex flex-wrap items-baseline justify-between gap-2 rounded-2xl glass-medium p-4"
              >
                <span className="font-medium">{booking.class_label}</span>
                <span className="text-sm text-[var(--text-secondary)]">
                  {formatClassDateTime(booking.starts_at)}
                  {booking.booking_status === "cancelled" ? " · отменено" : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

// Отдельная обычная функция, а не логика прямо в теле компонента: вызов
// Date.now() внутри функции компонента помечается линтером как нечистый.
// Предстоящие — подтверждённые будущие записи (как в боте); отменённые и
// прошедшие — в истории. Закрытие занятия для новых записей (slot_status
// "closed") существующую запись не отменяет.
function splitBookings(bookings: UserBooking[]) {
  const now = Date.now();
  const time = (booking: UserBooking) => new Date(booking.starts_at).getTime();
  const upcoming = bookings
    .filter((booking) => booking.booking_status === "confirmed" && time(booking) >= now)
    .sort((a, b) => time(a) - time(b));
  const history = bookings
    .filter((booking) => !upcoming.includes(booking))
    .sort((a, b) => time(b) - time(a));
  return { upcoming, history, now };
}

function UpcomingBooking({
  booking,
  canCancel,
  rebookCooldownHours,
}: {
  booking: UserBooking;
  canCancel: boolean;
  rebookCooldownHours: number;
}) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 rounded-2xl glass-medium p-4">
      <div className="flex flex-col gap-1">
        <span className="font-medium">{booking.class_label}</span>
        <span className="text-sm text-[var(--text-secondary)]">
          {formatClassDateTime(booking.starts_at)}
        </span>
        <span className="text-xs text-[var(--text-secondary)]">
          {canCancel
            ? `Отменить можно до ${formatClassDateTime(booking.cancellable_until)}`
            : "Отмена уже недоступна"}
        </span>
      </div>
      {canCancel && (
        <form action={cancelBookingAction}>
          <input type="hidden" name="slot_id" value={booking.slot_id} />
          <ConfirmSubmitButton
            confirmMessage={`Отменить запись на «${booking.class_label}», ${formatClassDateTime(booking.starts_at)}? Занятие вернётся на баланс. Записаться на это же занятие снова можно будет только через ${hoursLabel(rebookCooldownHours)}.`}
            className="text-sm font-medium text-[var(--danger)] hover:underline"
          >
            Отменить запись
          </ConfirmSubmitButton>
        </form>
      )}
    </li>
  );
}
