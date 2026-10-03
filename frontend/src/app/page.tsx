import Link from "next/link";
import { getSchedule } from "@/lib/api";
import { getCurrentUser } from "@/lib/auth";
import { getDirections } from "@/lib/directions";
import { CONTACTS } from "@/lib/contacts";
import { GLASS_BUTTON_CLASS } from "@/lib/glass";
import { BookableScheduleList } from "@/components/BookableScheduleList";
import { DirectionsStackCarousel } from "@/components/DirectionsStackCarousel";
import { HomeStory } from "@/components/HomeStory";
import { HomeStage } from "@/components/home/HomeStage";

const TELEGRAM_BOT_USERNAME = process.env.NEXT_PUBLIC_TELEGRAM_BOT_USERNAME;

// Расписание и абонементы меняются (места заполняются, цены может менять
// студия), поэтому страницу нельзя кэшировать статически на этапе сборки —
// см. frontend/README.md.
export const dynamic = "force-dynamic";

const WHY_US = [
  {
    icon: "group" as const,
    text: "Небольшие группы и внимание к технике каждого ученика.",
  },
  {
    icon: "levels" as const,
    text: "Занятия для любого уровня — от первого шага до постановки номера.",
  },
  {
    icon: "calendar" as const,
    text: "Гибкое расписание и возможность индивидуальных занятий.",
  },
  {
    icon: "telegram" as const,
    text: "Личный кабинет, онлайн-запись и абонементы — через тот же Telegram-аккаунт, что и в боте студии.",
  },
];

// Главная = сцена (HomeStage, позади) + контент (поверх). Секции ниже —
// "кадры" для хореографии HomeStory: data-scene задаёт якоря прогресса,
// data-sb — элементы контента, которые в неё вплетены.
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

  return (
    <HomeStory>
      <div className="relative">
        <HomeStage />

        <div className="home-content">
          {/* Hero: в живом режиме секция выше экрана (см. globals.css,
              [data-story-live] [data-scene="hero"]) ровно настолько,
              сколько нужно для перехода в About — текст прилипает к
              экрану, пока сцена позади "раскручивается" в следующую. */}
          <section data-scene="hero" className="stage-dark relative">
            <div className="sticky top-0 flex h-[100dvh] items-center">
              <div className="mx-auto w-full max-w-6xl px-4">
                <div data-sb="hero-text" className="stage-copy flex max-w-xl flex-col items-start gap-5 text-left">
                  <span className="eyebrow">Студия фламенко</span>
                  <h1 className="font-heading text-5xl font-bold leading-[1.05] tracking-tight sm:text-6xl lg:text-7xl">
                    Mirada Studio
                  </h1>
                  <p className="text-lg leading-relaxed text-[var(--text-secondary)] sm:text-xl">
                    Танец фламенко для начинающих и продолжающих: живой ритм,
                    работа с телом и характером — в группе или индивидуально.
                  </p>
                  <div className="mt-2 flex flex-wrap gap-3">
                    <Link
                      href={heroCtaHref}
                      className="rounded-full bg-[var(--primary)] px-7 py-3.5 text-base font-semibold text-[var(--on-primary)] shadow-[var(--shadow-card)] transition hover:-translate-y-0.5 hover:bg-[var(--primary-hover)] hover:shadow-[var(--shadow-card-hover)]"
                    >
                      {heroCtaLabel}
                    </Link>
                    {TELEGRAM_BOT_USERNAME && (
                      <a
                        href={`https://t.me/${TELEGRAM_BOT_USERNAME}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={`${GLASS_BUTTON_CLASS} glass-float px-7 py-3.5 text-base font-semibold`}
                      >
                        Написать в Telegram
                      </a>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </section>

          <section data-scene="about" className="px-4 py-20">
            <div className="glass-medium mx-auto flex w-full max-w-5xl flex-col justify-center rounded-[32px] p-8 sm:p-12">
              <div data-sb="about-heading" className="mb-6 flex flex-col items-center gap-3 text-center">
                <span className="eyebrow">О нас</span>
                <h2 className="font-heading text-3xl font-bold tracking-tight sm:text-4xl">
                  Почему мы?
                </h2>
              </div>
              <p
                data-sb="about-intro"
                className="mx-auto mb-10 max-w-2xl text-center text-base leading-relaxed text-[var(--text-secondary)]"
              >
                Mirada Studio — пространство для тех, кто хочет танцевать
                фламенко в своём темпе: от первого урока до сцены.
                Онлайн-запись, абонементы и личный кабинет — всё в одном
                месте, через тот же Telegram-аккаунт, что и в боте студии.
              </p>
              <div className="grid gap-8 sm:grid-cols-2">
                {WHY_US.map((item, i) => (
                  <div
                    key={item.text}
                    data-sb="about-tile"
                    className="flex flex-col items-center gap-3 text-center"
                  >
                    <WhyUsIcon variant={item.icon} index={i} />
                    <p className="text-base leading-relaxed text-[var(--text-secondary)]">
                      {item.text}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </section>

          <section
            id="directions"
            data-scene="directions"
            className="mx-auto w-full max-w-5xl scroll-mt-24 px-4 py-20"
          >
            <div data-sb="directions-heading" className="mb-10 flex flex-col items-center gap-3 text-center">
              <span className="eyebrow">Наши направления</span>
              <h2 className="font-heading text-3xl font-bold tracking-tight sm:text-4xl">
                Выберите подходящее
              </h2>
            </div>
            <div data-sb="directions-stage">
              <DirectionsStackCarousel directions={directions} />
            </div>
          </section>

          <section data-scene="schedule" className="mx-auto w-full max-w-5xl px-4 py-20">
            <div data-sb="schedule-heading" className="mb-10 flex flex-col items-center gap-3 text-center">
              <span className="eyebrow">Расписание</span>
              <h2 className="font-heading text-3xl font-bold tracking-tight sm:text-4xl">
                Ближайшие занятия
              </h2>
            </div>
            <div data-sb="schedule-stage">
              <BookableScheduleList
                slots={upcoming}
                isAuthenticated={currentUser !== null}
                classKey={null}
              />
            </div>
          </section>

          {/* Финал: снова тёмная сцена — веер складывается и уходит вниз
              (см. HomeStory), контент — в левой колонке. */}
          <section data-scene="cta" className="stage-dark py-24">
            <div className="mx-auto w-full max-w-6xl px-4">
              <div className="stage-copy flex max-w-xl flex-col items-center gap-6 text-center lg:items-start lg:text-left">
                <div data-sb="cta-heading" className="flex flex-col items-center gap-3 lg:items-start">
                  <span className="eyebrow">Готовы начать?</span>
                  <h2 className="font-heading text-3xl font-bold tracking-tight sm:text-4xl">
                    Контакты
                  </h2>
                  <p className="max-w-md text-[var(--text-secondary)]">
                    Свяжитесь со студией любым удобным способом — поможем
                    выбрать направление и время занятия.
                  </p>
                </div>
                {TELEGRAM_BOT_USERNAME && (
                  <a
                    data-sb="cta-button"
                    href={`https://t.me/${TELEGRAM_BOT_USERNAME}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex w-fit items-center gap-2 rounded-full bg-[var(--primary)] px-6 py-3 text-base font-semibold text-[var(--on-primary)] shadow-[var(--shadow-card)] transition hover:-translate-y-0.5 hover:bg-[var(--primary-hover)] hover:shadow-[var(--shadow-card-hover)]"
                  >
                    Написать в Telegram
                  </a>
                )}
                <div data-sb="cta-contacts" className="glass-medium w-full rounded-[28px] p-6 [text-shadow:none] sm:p-7">
                  <dl className="flex flex-col gap-3 text-left">
                    <ContactRow label="Адрес" value={CONTACTS.address} />
                    <ContactRow label="Телефон" value={CONTACTS.phone} />
                    <ContactRow
                      label="Telegram"
                      value={TELEGRAM_BOT_USERNAME ? `@${TELEGRAM_BOT_USERNAME}` : "Ссылка уточняется"}
                    />
                  </dl>
                </div>
              </div>
            </div>
          </section>
        </div>
      </div>
    </HomeStory>
  );
}

// Иконки для "Почему мы?" — разные и по теме каждого пункта (группы,
// уровни, расписание, Telegram-бронирование), а не одна и та же картинка
// на всех плитках. Пока это неоновые иконки, не фотографии: реальных фото
// студии/преподавателей в проекте нет, выдумывать их нельзя (CLAUDE.md §27).
function WhyUsIcon({
  variant,
  index,
}: {
  variant: "group" | "levels" | "calendar" | "telegram";
  index: number;
}) {
  return (
    <div
      className="icon-float flex h-16 w-16 items-center justify-center rounded-2xl bg-[var(--primary-light)] text-[var(--accent-dark)]"
      style={{ animationDelay: `${index * 450}ms` }}
      aria-hidden="true"
    >
      <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        {variant === "group" && (
          <>
            <circle cx="8.5" cy="8" r="2.8" />
            <circle cx="16" cy="9.3" r="2.2" />
            <path d="M3 19c0-3.1 2.5-5.3 5.5-5.3s5.5 2.2 5.5 5.3" />
            <path d="M14.5 14.3c2.1.4 3.5 2.3 3.5 4.7" />
          </>
        )}
        {variant === "levels" && (
          <>
            <rect x="4" y="13" width="3.2" height="7" rx="0.6" />
            <rect x="10.4" y="9" width="3.2" height="11" rx="0.6" />
            <rect x="16.8" y="4.5" width="3.2" height="15.5" rx="0.6" />
          </>
        )}
        {variant === "calendar" && (
          <>
            <rect x="3.5" y="5" width="17" height="15" rx="2" />
            <path d="M3.5 9.5h17M8 3v4M16 3v4" />
          </>
        )}
        {variant === "telegram" && <path d="M21.5 2.5 10.8 13.2M21.5 2.5 15 21.5l-4.2-8.3-8.3-4.2z" />}
      </svg>
    </div>
  );
}

function ContactRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1 sm:flex-row sm:gap-3">
      <dt className="w-24 shrink-0 font-medium">{label}</dt>
      <dd className="text-[var(--text-secondary)]">{value}</dd>
    </div>
  );
}
