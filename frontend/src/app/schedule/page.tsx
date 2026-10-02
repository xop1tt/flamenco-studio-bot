import type { Metadata } from "next";
import Link from "next/link";
import { getSchedule } from "@/lib/api";
import { ScheduleList } from "@/components/ScheduleList";
import { DIRECTIONS } from "@/lib/directions";

export const metadata: Metadata = {
  title: "Расписание",
};

// Свободные места меняются в реальном времени — не кэшируем статически.
export const dynamic = "force-dynamic";

type SearchParams = Promise<{ class_key?: string }>;

export default async function SchedulePage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const { class_key: classKey } = await searchParams;
  const activeDirection = DIRECTIONS.find(
    (direction) => direction.key === classKey,
  );
  const schedule = await getSchedule(activeDirection?.key);

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-12">
      <h1 className="text-3xl font-bold">Расписание</h1>

      <div className="flex flex-wrap gap-2">
        <FilterLink label="Все направления" active={!activeDirection} />
        {DIRECTIONS.map((direction) => (
          <FilterLink
            key={direction.key}
            label={direction.label}
            classKey={direction.key}
            active={activeDirection?.key === direction.key}
          />
        ))}
      </div>

      <ScheduleList slots={schedule} />
    </div>
  );
}

function FilterLink({
  label,
  classKey,
  active,
}: {
  label: string;
  classKey?: string;
  active: boolean;
}) {
  const href = classKey ? `/schedule?class_key=${classKey}` : "/schedule";
  return (
    <Link
      href={href}
      className={
        active
          ? "rounded-full bg-[var(--accent)] px-4 py-1.5 text-sm font-medium text-white"
          : "rounded-full border border-black/15 px-4 py-1.5 text-sm font-medium transition hover:border-[var(--accent)] hover:text-[var(--accent)]"
      }
    >
      {label}
    </Link>
  );
}
