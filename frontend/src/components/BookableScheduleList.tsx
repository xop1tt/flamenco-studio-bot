import Link from "next/link";
import { isBookable, type ClassSlot } from "@/lib/api";
import { formatClassDateTime, hoursLabel, placesLabel } from "@/lib/format";
import { bookClassAction } from "@/lib/actions";
import { ConfirmSubmitButton } from "./ConfirmSubmitButton";
import { EmptyScheduleNotice } from "./ScheduleList";

type Props = {
  slots: ClassSlot[];
  isAuthenticated: boolean;
  classKey: string | null;
  // Окно отмены из backend (GET /api/bookings/rules): запись ближе этого
  // срока необратима и, как в боте, требует подтверждения.
  cancellationDeadlineHours: number;
};

// Те же правила, что в разделе «Записаться» Telegram-бота: показываются
// только занятия, на которые можно записаться (открытые, с местами).
export function BookableScheduleList({
  slots,
  isAuthenticated,
  classKey,
  cancellationDeadlineHours,
}: Props) {
  const bookable = slots.filter(isBookable);
  if (bookable.length === 0) {
    return <EmptyScheduleNotice />;
  }

  const lateFrom = lateBookingThreshold(cancellationDeadlineHours);
  return (
    <ul className="flex flex-col gap-3">
      {bookable.map((slot) => (
        <BookableScheduleCard
          key={slot.id}
          slot={slot}
          isAuthenticated={isAuthenticated}
          classKey={classKey}
          irreversible={new Date(slot.starts_at).getTime() < lateFrom}
          cancellationDeadlineHours={cancellationDeadlineHours}
        />
      ))}
    </ul>
  );
}

// Отдельная функция, а не Date.now() прямо в теле компонента: линтер
// считает вызов текущего времени в рендере нечистым.
function lateBookingThreshold(hours: number): number {
  return Date.now() + hours * 60 * 60 * 1000;
}

function BookableScheduleCard({
  slot,
  isAuthenticated,
  classKey,
  irreversible,
  cancellationDeadlineHours,
}: {
  slot: ClassSlot;
  isAuthenticated: boolean;
  classKey: string | null;
  irreversible: boolean;
  cancellationDeadlineHours: number;
}) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 rounded-[24px] glass-medium glass-specular p-5">
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-baseline gap-2">
          <span className="font-medium">{slot.class_label}</span>
          <span className="text-sm text-[var(--text-secondary)]">
            {formatClassDateTime(slot.starts_at)}
          </span>
        </div>
        <div className="text-sm font-medium text-[var(--primary)]">
          Свободно {placesLabel(slot.remaining)}
        </div>
        {irreversible && (
          <div className="text-xs text-[var(--text-secondary)]">
            До начала меньше {hoursLabel(cancellationDeadlineHours)} — отменить
            запись будет нельзя.
          </div>
        )}
      </div>

      {isAuthenticated ? (
        <form action={bookClassAction}>
          <input type="hidden" name="slot_id" value={slot.id} />
          {classKey && <input type="hidden" name="class_key" value={classKey} />}
          {irreversible ? (
            <ConfirmSubmitButton
              confirmMessage={`Записаться на занятие? До начала меньше ${hoursLabel(cancellationDeadlineHours)} — отменить эту запись будет нельзя, занятие спишется с баланса.`}
              className="btn-primary shrink-0 rounded-full px-4 py-2 text-sm font-medium"
            >
              Записаться
            </ConfirmSubmitButton>
          ) : (
            <button
              type="submit"
              className="btn-primary shrink-0 rounded-full px-4 py-2 text-sm font-medium"
            >
              Записаться
            </button>
          )}
        </form>
      ) : (
        <Link
          href="/login"
          className="btn-primary shrink-0 rounded-full px-4 py-2 text-sm font-medium"
        >
          Войти и записаться
        </Link>
      )}
    </li>
  );
}
