import Link from "next/link";
import type { ClassSlot } from "@/lib/api";
import { formatClassDateTime } from "@/lib/format";

// Единый текст для пустого расписания — используется и на главной, и на
// /schedule, чтобы не показывать разные сообщения об одном и том же факте
// (то, что занятий пока нет).
export function EmptyScheduleNotice() {
  return (
    <div className="glass-medium flex flex-col items-start gap-3 rounded-[24px] p-6">
      <p className="text-[var(--text-secondary)]">
        Подбираем ближайшие группы. Оставьте заявку — пришлём удобные
        варианты, как только расписание сформируется.
      </p>
      <Link
        href="/contact"
        className="rounded-full bg-[var(--primary)] px-5 py-2 text-sm font-medium text-[var(--on-primary)] shadow-[var(--shadow-card)] transition hover:bg-[var(--primary-hover)] hover:shadow-[var(--shadow-card-hover)]"
      >
        Написать, чтобы подобрать время
      </Link>
    </div>
  );
}

export function availabilityLabel(slot: ClassSlot): string {
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
    <li className="flex flex-col gap-2 rounded-[24px] glass-medium glass-specular p-5 transition hover:-translate-y-0.5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
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
    </li>
  );
}

export function ScheduleList({ slots }: { slots: ClassSlot[] }) {
  if (slots.length === 0) {
    return <EmptyScheduleNotice />;
  }

  return (
    <ul className="flex flex-col gap-3">
      {slots.map((slot) => (
        <ScheduleCard key={slot.id} slot={slot} />
      ))}
    </ul>
  );
}
