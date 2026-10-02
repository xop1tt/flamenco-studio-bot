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

  const whyUs = [
    {
      icon: "👥",
      text: "Небольшие группы и внимание к технике каждого ученика.",
    },
    {
      icon: "🌱",
      text: "Занятия для любого уровня — от первого шага до постановки номера.",
    },
    {
      icon: "🗓️",
      text: "Гибкое расписание и возможность индивидуальных занятий.",
    },
  ];

  return (
    <div className="flex flex-col gap-16 px-4 py-12">
      <section className="mx-auto flex max-w-3xl flex-col items-center gap-4 text-center">
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
          Flamenco Studio
        </h1>
        <p className="max-w-xl text-lg leading-relaxed text-[var(--text-secondary)]">
          Танец фламенко для начинающих и продолжающих: живой ритм, работа с
          телом и характером — в группе или индивидуально.
        </p>
        <div className="mt-2 flex flex-wrap justify-center gap-3">
          <Link
            href="/schedule"
            className="rounded-full bg-[var(--primary)] px-6 py-3 font-medium text-[var(--surface)] shadow-[var(--shadow-card)] transition hover:bg-[var(--primary-hover)] hover:shadow-[var(--shadow-card-hover)]"
          >
            Смотреть расписание
          </Link>
          <Link
            href="/packages"
            className="rounded-full border border-[var(--border-strong)] bg-[var(--surface)] px-6 py-3 font-medium transition hover:border-[var(--primary)] hover:text-[var(--primary)]"
          >
            Абонементы
          </Link>
        </div>
      </section>

      <section className="mx-auto w-full max-w-5xl rounded-3xl bg-[var(--surface-secondary)] p-8 sm:p-10">
        <h2 className="mb-6 text-center text-2xl font-semibold">
          Почему Flamenco Studio
        </h2>
        <div className="grid gap-6 sm:grid-cols-3">
          {whyUs.map((item) => (
            <div key={item.text} className="flex flex-col items-center gap-3 text-center">
              <span className="flex h-12 w-12 items-center justify-center rounded-full bg-[var(--primary-light)] text-2xl">
                {item.icon}
              </span>
              <p className="text-base leading-relaxed text-[var(--text-secondary)]">
                {item.text}
              </p>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto w-full max-w-5xl">
        <h2 className="mb-6 text-2xl font-semibold">Направления</h2>
        <div className="grid gap-4 sm:grid-cols-3">
          {directions.map((direction) => (
            <div
              key={direction.key}
              className="rounded-2xl border border-[var(--border-strong)] bg-[var(--surface)] p-5 shadow-[var(--shadow-card)] transition hover:-translate-y-0.5 hover:shadow-[var(--shadow-card-hover)]"
            >
              <h3 className="mb-2 font-medium">{direction.label}</h3>
              <p className="text-base text-[var(--text-secondary)]">
                {direction.description}
              </p>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto w-full max-w-5xl">
        <div className="mb-6 flex items-baseline justify-between">
          <h2 className="text-2xl font-semibold">Ближайшие занятия</h2>
          <Link
            href="/schedule"
            className="text-sm font-medium text-[var(--primary)] hover:underline"
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
            className="text-sm font-medium text-[var(--primary)] hover:underline"
          >
            Все варианты →
          </Link>
        </div>
        <PackagesGrid packages={packages.slice(0, 3)} />
      </section>

      <section className="mx-auto flex w-full max-w-3xl flex-col items-center gap-3 rounded-3xl bg-[var(--primary-light)] p-10 text-center shadow-[var(--shadow-card)]">
        <h2 className="text-2xl font-semibold text-[var(--accent-dark)]">
          Готовы начать?
        </h2>
        <p className="text-[var(--text-secondary)]">
          Выберите удобное занятие в расписании или напишите нам — поможем
          выбрать направление.
        </p>
        <Link
          href="/contact"
          className="mt-2 rounded-full bg-[var(--primary)] px-6 py-3 font-medium text-[var(--surface)] shadow-[var(--shadow-card)] transition hover:bg-[var(--primary-hover)] hover:shadow-[var(--shadow-card-hover)]"
        >
          Связаться со студией
        </Link>
      </section>
    </div>
  );
}
