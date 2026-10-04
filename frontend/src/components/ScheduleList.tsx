import Link from "next/link";

// Единый текст для пустого расписания — используется и на главной, и на
// /schedule, чтобы не показывать разные сообщения об одном и том же факте
// (то, что свободных занятий пока нет).
export function EmptyScheduleNotice() {
  return (
    <div className="glass-medium flex flex-col items-start gap-3 rounded-[24px] p-6">
      <p className="text-[var(--text-secondary)]">
        Сейчас свободных занятий нет — подбираем ближайшие группы. Оставьте
        заявку, и мы пришлём удобные варианты, как только расписание
        сформируется.
      </p>
      <Link
        href="/contact"
        className="btn-primary rounded-full px-5 py-2 text-sm font-medium"
      >
        Написать, чтобы подобрать время
      </Link>
    </div>
  );
}
