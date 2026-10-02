import Link from "next/link";
import { getPackages, getSchedule } from "@/lib/api";
import { ScheduleList } from "@/components/ScheduleList";
import { PackagesGrid } from "@/components/PackagesGrid";
import { getDirections } from "@/lib/directions";

// Расписание и абонементы меняются (места заполняются, цены может менять
// студия), поэтому страницу нельзя кэшировать статически на этапе сборки —
// см. frontend/README.md.
export const dynamic = "force-dynamic";

export default async function HomePage() {
  const [schedule, packages, directions] = await Promise.all([
    getSchedule(),
    getPackages(),
    getDirections(),
  ]);
  const upcoming = schedule.slice(0, 4);

  return (
    <div className="flex flex-col gap-16 px-4 py-12">
      <section className="mx-auto flex max-w-3xl flex-col items-center gap-4 text-center">
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
          Flamenco Studio
        </h1>
        <p className="max-w-xl text-lg text-[var(--foreground)]/80">
          Танец фламенко для начинающих и продолжающих: живой ритм, работа с
          телом и характером — в группе или индивидуально.
        </p>
        <div className="mt-2 flex flex-wrap justify-center gap-3">
          <Link
            href="/schedule"
            className="rounded-md bg-[var(--accent)] px-5 py-2.5 font-medium text-white transition hover:opacity-90"
          >
            Смотреть расписание
          </Link>
          <Link
            href="/packages"
            className="rounded-md border border-black/15 px-5 py-2.5 font-medium transition hover:border-[var(--accent)] hover:text-[var(--accent)]"
          >
            Абонементы
          </Link>
        </div>
      </section>

      <section className="mx-auto w-full max-w-5xl">
        <h2 className="mb-6 text-2xl font-semibold">Направления</h2>
        <div className="grid gap-4 sm:grid-cols-3">
          {directions.map((direction) => (
            <div
              key={direction.key}
              className="rounded-lg border border-black/10 p-5"
            >
              <h3 className="mb-2 font-medium">{direction.label}</h3>
              <p className="text-sm text-[var(--foreground)]/70">
                {direction.description}
              </p>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto w-full max-w-5xl">
        <h2 className="mb-2 text-2xl font-semibold">Почему Flamenco Studio</h2>
        <div className="grid gap-4 sm:grid-cols-3">
          <p className="text-sm text-[var(--foreground)]/80">
            Небольшие группы и внимание к технике каждого ученика.
          </p>
          <p className="text-sm text-[var(--foreground)]/80">
            Занятия для любого уровня — от первого шага до постановки номера.
          </p>
          <p className="text-sm text-[var(--foreground)]/80">
            Гибкое расписание и возможность индивидуальных занятий.
          </p>
        </div>
      </section>

      <section className="mx-auto w-full max-w-5xl">
        <div className="mb-6 flex items-baseline justify-between">
          <h2 className="text-2xl font-semibold">Ближайшие занятия</h2>
          <Link
            href="/schedule"
            className="text-sm font-medium text-[var(--accent)] hover:underline"
          >
            Всё расписание →
          </Link>
        </div>
        <ScheduleList slots={upcoming} />
      </section>

      <section className="mx-auto w-full max-w-5xl">
        <div className="mb-6 flex items-baseline justify-between">
          <h2 className="text-2xl font-semibold">Абонементы</h2>
          <Link
            href="/packages"
            className="text-sm font-medium text-[var(--accent)] hover:underline"
          >
            Все варианты →
          </Link>
        </div>
        <PackagesGrid packages={packages.slice(0, 3)} />
      </section>

      <section className="mx-auto flex w-full max-w-3xl flex-col items-center gap-3 rounded-lg border border-black/10 p-8 text-center">
        <h2 className="text-2xl font-semibold">Готовы начать?</h2>
        <p className="text-[var(--foreground)]/70">
          Выберите удобное занятие в расписании или напишите нам — поможем
          выбрать направление.
        </p>
        <Link
          href="/contact"
          className="mt-2 rounded-md bg-[var(--accent)] px-5 py-2.5 font-medium text-white transition hover:opacity-90"
        >
          Связаться со студией
        </Link>
      </section>
    </div>
  );
}
