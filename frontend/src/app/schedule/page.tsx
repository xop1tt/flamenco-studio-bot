import type { Metadata } from "next";
import Link from "next/link";
import { getSchedule } from "@/lib/api";
import { getCurrentUser } from "@/lib/auth";
import { BookableScheduleList } from "@/components/BookableScheduleList";
import { getDirections } from "@/lib/directions";

export const metadata: Metadata = {
  title: "Расписание",
};

// Свободные места меняются в реальном времени — не кэшируем статически.
export const dynamic = "force-dynamic";

type SearchParams = Promise<{
  class_key?: string;
  booked?: string;
  already?: string;
  book_error?: string;
}>;

export default async function SchedulePage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const {
    class_key: classKey,
    booked,
    already,
    book_error: bookError,
  } = await searchParams;
  const directions = await getDirections();
  const activeDirection = directions.find(
    (direction) => direction.key === classKey,
  );
  const [schedule, currentUser] = await Promise.all([
    getSchedule(activeDirection?.key),
    getCurrentUser(),
  ]);

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-12">
      <h1 className="text-3xl font-bold">Расписание</h1>

      {booked && (
        <p className="rounded-md bg-green-50 p-3 text-sm text-green-800">
          {already === "1"
            ? "Вы уже были записаны на это занятие."
            : "Место подтверждено! Занятие появится в «Мои занятия»."}
        </p>
      )}
      {bookError && (
        <p className="rounded-md bg-red-50 p-3 text-sm text-red-800">
          {bookError}
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        <FilterLink label="Все направления" active={!activeDirection} />
        {directions.map((direction) => (
          <FilterLink
            key={direction.key}
            label={direction.label}
            classKey={direction.key}
            active={activeDirection?.key === direction.key}
          />
        ))}
      </div>

      <BookableScheduleList
        slots={schedule}
        isAuthenticated={currentUser !== null}
        classKey={activeDirection?.key ?? null}
      />
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
          ? "rounded-full bg-[var(--primary)] px-4 py-1.5 text-sm font-medium text-[var(--surface)]"
          : "rounded-full border border-[var(--border-strong)] px-4 py-1.5 text-sm font-medium transition hover:border-[var(--primary)] hover:text-[var(--primary)]"
      }
    >
      {label}
    </Link>
  );
}
