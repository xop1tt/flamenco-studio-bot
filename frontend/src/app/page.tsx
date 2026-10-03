import Link from "next/link";
import { getSchedule } from "@/lib/api";
import { getCurrentUser } from "@/lib/auth";
import { BookableScheduleList } from "@/components/BookableScheduleList";
import { getDirections } from "@/lib/directions";
import { DirectionsStackCarousel } from "@/components/DirectionsStackCarousel";

const TELEGRAM_BOT_USERNAME = process.env.NEXT_PUBLIC_TELEGRAM_BOT_USERNAME;

// Расписание и абонементы меняются (места заполняются, цены может менять
// студия), поэтому страницу нельзя кэшировать статически на этапе сборки —
// см. frontend/README.md.
export const dynamic = "force-dynamic";

export default async function HomePage() {
  const [schedule, directions, currentUser] = await Promise.all([
    getSchedule(),
    getDirections(),
    getCurrentUser(),
  ]);
  const upcoming = schedule.slice(0, 4);
  // Пока расписание пустое, вести главный CTA в расписание некуда —
  // ведём туда, где можно реально оставить заявку (см. аудит, пункт 3.2).
  const heroCtaHref = schedule.length > 0 ? "/schedule" : "/contact";
  const heroCtaLabel =
    schedule.length > 0 ? "Записаться на занятие" : "Оставить заявку";

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
        <h1 className="font-heading text-4xl font-bold tracking-tight sm:text-5xl">
          Mirada Studio
        </h1>
        <p className="max-w-xl text-lg leading-relaxed text-[var(--text-secondary)]">
          Танец фламенко для начинающих и продолжающих: живой ритм, работа с
          телом и характером — в группе или индивидуально.
        </p>
        <div className="mt-2 flex flex-wrap justify-center gap-3">
          <Link
            href={heroCtaHref}
            className="rounded-full bg-[var(--primary)] px-6 py-3 text-base font-semibold text-[var(--on-primary)] shadow-[var(--shadow-card)] transition hover:bg-[var(--primary-hover)] hover:shadow-[var(--shadow-card-hover)]"
          >
            {heroCtaLabel}
          </Link>
          {TELEGRAM_BOT_USERNAME && (
            <a
              href={`https://t.me/${TELEGRAM_BOT_USERNAME}`}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-full border border-[var(--border-strong)] bg-[var(--surface)] px-6 py-3 text-base font-semibold transition hover:border-[var(--primary)] hover:text-[var(--primary)]"
            >
              Написать в Telegram
            </a>
          )}
        </div>
      </section>

      <section className="glass-card mx-auto w-full max-w-5xl rounded-3xl p-8 shadow-[var(--shadow-card)] sm:p-10">
        <h2 className="mb-6 text-center text-2xl font-semibold">
          Почему мы?
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

      <section id="directions" className="mx-auto w-full max-w-5xl scroll-mt-24">
        <h2 className="mb-6 text-center text-2xl font-semibold">Направления</h2>
        <DirectionsStackCarousel directions={directions} />
      </section>

      <section className="mx-auto w-full max-w-5xl">
        <h2 className="mb-6 text-center text-2xl font-semibold">Ближайшие занятия</h2>
        <BookableScheduleList
          slots={upcoming}
          isAuthenticated={currentUser !== null}
          classKey={null}
        />
      </section>

      <section className="glass-card-accent mx-auto flex w-full max-w-3xl flex-col items-center gap-3 rounded-3xl p-10 text-center shadow-[var(--shadow-card)]">
        <h2 className="text-2xl font-semibold text-[var(--accent-dark)]">
          Готовы начать?
        </h2>
        <p className="text-[var(--text-secondary)]">
          Выберите удобное занятие в расписании или напишите нам — поможем
          выбрать направление.
        </p>
        <Link
          href="/contact"
          className="mt-2 rounded-full bg-[var(--primary)] px-6 py-3 font-medium text-[var(--on-primary)] shadow-[var(--shadow-card)] transition hover:bg-[var(--primary-hover)] hover:shadow-[var(--shadow-card-hover)]"
        >
          Связаться со студией
        </Link>
      </section>
    </div>
  );
}
