import type { ClassSlot } from "@/lib/api";
import { formatClassDateTime } from "@/lib/format";

function availabilityLabel(slot: ClassSlot): string {
  if (slot.status !== "open") {
    return "Занятие закрыто";
  }
  if (slot.remaining <= 0) {
    return "Мест нет";
  }
  return `Свободно: ${slot.remaining} из ${slot.capacity}`;
}

export function ScheduleCard({ slot }: { slot: ClassSlot }) {
  const soldOut = slot.status !== "open" || slot.remaining <= 0;

  return (
    <li className="flex flex-col gap-2 rounded-lg border border-black/10 p-4 shadow-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="font-medium">{slot.class_label}</span>
        <span className="text-sm text-[var(--foreground)]/70">
          {formatClassDateTime(slot.starts_at)}
        </span>
      </div>
      <div
        className={
          soldOut
            ? "text-sm text-[var(--foreground)]/60"
            : "text-sm font-medium text-[var(--accent)]"
        }
      >
        {availabilityLabel(slot)}
      </div>
    </li>
  );
}

export function ScheduleList({ slots }: { slots: ClassSlot[] }) {
  if (slots.length === 0) {
    return (
      <p className="text-[var(--foreground)]/70">
        Сейчас нет запланированных занятий. Загляните позже или напишите нам
        — см. страницу «Контакты».
      </p>
    );
  }

  return (
    <ul className="flex flex-col gap-3">
      {slots.map((slot) => (
        <ScheduleCard key={slot.id} slot={slot} />
      ))}
    </ul>
  );
}
