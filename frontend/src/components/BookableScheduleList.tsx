import Link from "next/link";
import type { ClassSlot } from "@/lib/api";
import { formatClassDateTime } from "@/lib/format";
import { bookClassAction } from "@/lib/actions";
import { availabilityLabel, EmptyScheduleNotice } from "./ScheduleList";

type Props = {
  slots: ClassSlot[];
  isAuthenticated: boolean;
  classKey: string | null;
};

export function BookableScheduleList({ slots, isAuthenticated, classKey }: Props) {
  if (slots.length === 0) {
    return <EmptyScheduleNotice />;
  }

  return (
    <ul className="flex flex-col gap-3">
      {slots.map((slot) => (
        <BookableScheduleCard
          key={slot.id}
          slot={slot}
          isAuthenticated={isAuthenticated}
          classKey={classKey}
        />
      ))}
    </ul>
  );
}

function BookableScheduleCard({
  slot,
  isAuthenticated,
  classKey,
}: {
  slot: ClassSlot;
  isAuthenticated: boolean;
  classKey: string | null;
}) {
  const bookable = slot.status === "open" && slot.remaining > 0;
  const soldOut = !bookable;

  return (
    <li className="flex flex-wrap items-center justify-between gap-3 rounded-2xl glass-card p-4 shadow-[var(--shadow-card)] transition hover:shadow-[var(--shadow-card-hover)]">
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-baseline gap-2">
          <span className="font-medium">{slot.class_label}</span>
          <span className="text-sm text-[var(--text-secondary)]">
            {formatClassDateTime(slot.starts_at)}
          </span>
        </div>
        <div
          className={
            soldOut
              ? "text-sm text-[var(--text-secondary)]"
              : "text-sm font-medium text-[var(--primary)]"
          }
        >
          {availabilityLabel(slot)}
        </div>
      </div>

      {bookable &&
        (isAuthenticated ? (
          <form action={bookClassAction}>
            <input type="hidden" name="slot_id" value={slot.id} />
            {classKey && <input type="hidden" name="class_key" value={classKey} />}
            <button
              type="submit"
              className="shrink-0 rounded-full bg-[var(--primary)] px-4 py-2 text-sm font-medium text-[var(--on-primary)] shadow-[var(--shadow-card)] transition hover:bg-[var(--primary-hover)] hover:shadow-[var(--shadow-card-hover)]"
            >
              Записаться
            </button>
          </form>
        ) : (
          <Link
            href="/login"
            className="shrink-0 rounded-full bg-[var(--primary)] px-4 py-2 text-sm font-medium text-[var(--on-primary)] shadow-[var(--shadow-card)] transition hover:bg-[var(--primary-hover)] hover:shadow-[var(--shadow-card-hover)]"
          >
            Войти и записаться
          </Link>
        ))}
    </li>
  );
}
