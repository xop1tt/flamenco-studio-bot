import Link from "next/link";
import type { ReactNode } from "react";
import { getSchedule } from "@/lib/api";
import { getCurrentUser } from "@/lib/auth";
import { getDirections } from "@/lib/directions";
import { CONTACTS } from "@/lib/contacts";
import { formatClassDateTime } from "@/lib/format";
import { GLASS_BUTTON_CLASS, PRIMARY_BUTTON_CLASS } from "@/lib/glass";
import { BookableScheduleList } from "@/components/BookableScheduleList";
import { DirectionsStackCarousel } from "@/components/DirectionsStackCarousel";
import { HomeStory, type SceneLink } from "@/components/HomeStory";
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
];

// Сцены главной по порядку — id секции = якорь (/#directions) и подпись
// точки в навигации по сценам.
const SCENES: SceneLink[] = [
  { id: "hero", label: "Начало" },
  { id: "directions", label: "Направления" },
  { id: "about", label: "О студии" },
  { id: "schedule", label: "Расписание" },
  { id: "contacts", label: "Контакты" },
];

// Главная — последовательность полноэкранных сцен (HomeStory): камера
// переходит из сцены в сцену, а не страница листается секциями. Внутри
// сцены data-layer — слои контента, которые хореография двигает с
// параллаксом по data-depth (больше — ближе к камере, быстрее), data-blur —
// слой можно размывать в переходе (только не стеклянные блоки: blur
// родителя ломает backdrop-filter стекла внутри него).
export default async function HomePage() {
  const [schedule, directions, currentUser] = await Promise.all([
    getSchedule(),
    getDirections(),
    getCurrentUser(),
  ]);
  const upcoming = schedule.slice(0, 4);
  const nextClass = schedule[0];
  // Пока расписание пустое, вести главный CTA в расписание некуда —
  // ведём туда, где можно реально оставить заявку (см. аудит, пункт 3.2).
  const heroCtaHref = schedule.length > 0 ? "/schedule" : "/contact";
  const heroCtaLabel =
    schedule.length > 0 ? "Записаться на занятие" : "Оставить заявку";

  return (
    <HomeStory stage={<HomeStage />} scenes={SCENES}>
      <Scene id="hero" dark labelledBy="hero-title">
        <div className="mx-auto w-full max-w-6xl px-5 sm:px-6">
          <div className="stage-copy flex max-w-xl flex-col items-start gap-4 text-left">
            <div data-layer data-depth="1" data-blur className="flex flex-col items-start gap-3">
              <span className="eyebrow">Студия фламенко</span>
              <h1
                id="hero-title"
                className="font-heading text-5xl font-bold leading-[1.05] tracking-tight sm:text-6xl lg:text-7xl"
              >
                Mirada Studio
              </h1>
            </div>
            <p
              data-layer
              data-depth="1.15"
              data-blur
              className="text-lg leading-relaxed text-[var(--text-secondary)] sm:text-xl"
            >
              Танец фламенко для начинающих и продолжающих: живой ритм,
              работа с телом и характером — в группе или индивидуально.
            </p>
            <div data-layer data-depth="1.3" className="mt-1 flex flex-wrap gap-3 [text-shadow:none]">
              <Link href={heroCtaHref} className={`${PRIMARY_BUTTON_CLASS} px-7 py-3.5 text-base`}>
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
            {nextClass && (
              <Link
                href="/schedule"
                data-layer
                data-depth="1.5"
                className="glass-subtle glass-float glass-interactive mt-2 inline-flex items-center gap-3 rounded-2xl px-4 py-2.5 text-sm [text-shadow:none]"
              >
                <span className="h-2 w-2 shrink-0 rounded-full bg-[var(--primary)]" aria-hidden="true" />
                <span className="flex flex-col">
                  <span className="text-xs uppercase tracking-[0.14em] text-[var(--text-muted)]">
                    Ближайшее занятие
                  </span>
                  <span className="font-medium">
                    {nextClass.class_label} · {formatClassDateTime(nextClass.starts_at)}
                  </span>
                </span>
              </Link>
            )}
          </div>
        </div>
        <div data-hint className="scroll-hint glass-subtle glass-float">
          <span>Листайте</span>
          <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M8 3v10M3.5 8.5 8 13l4.5-4.5" />
          </svg>
        </div>
      </Scene>

      <Scene id="directions" labelledBy="directions-title">
        <div className="mx-auto w-full max-w-5xl px-4">
          <div data-layer data-depth="0.8" data-blur className="mb-4 flex flex-col items-center gap-3 text-center">
            <span className="eyebrow">Наши направления</span>
            <h2 id="directions-title" className="font-heading text-3xl font-bold tracking-tight sm:text-4xl">
              Выберите подходящее
            </h2>
          </div>
          <div data-layer data-depth="1.15">
            <DirectionsStackCarousel directions={directions} />
          </div>
        </div>
      </Scene>

      <Scene id="about" labelledBy="about-title">
        <div className="mx-auto w-full max-w-5xl px-4">
          <div data-layer data-depth="1" className="glass-medium glass-float rounded-[32px] px-6 py-8 sm:p-12">
            <div data-layer data-depth="0.05" data-blur className="mb-3.5 flex flex-col items-center gap-3 text-center">
              <span className="eyebrow">О нас</span>
              <h2 id="about-title" className="font-heading text-3xl font-bold tracking-tight sm:text-4xl">
                Почему мы?
              </h2>
            </div>
            <p
              data-layer
              data-depth="0.08"
              data-blur
              className="mx-auto mb-7 max-w-2xl text-center text-base leading-relaxed text-[var(--text-secondary)]"
            >
              Mirada Studio — пространство для тех, кто хочет танцевать
              фламенко в своём темпе: от первого урока до сцены.
              Онлайн-запись, абонементы и личный кабинет — всё в одном
              месте, через тот же Telegram-аккаунт, что и в боте студии.
            </p>
            <div className="grid gap-6 sm:grid-cols-3">
              {WHY_US.map((item, i) => (
                <div
                  key={item.text}
                  data-layer
                  data-depth={(0.1 + i * 0.04).toFixed(2)}
                  data-blur
                  className="flex flex-col items-center gap-3 text-center"
                >
                  <WhyUsIcon variant={item.icon} />
                  <p className="text-base leading-relaxed text-[var(--text-secondary)]">
                    {item.text}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </Scene>

      <Scene id="schedule" labelledBy="schedule-title">
        <div className="mx-auto w-full max-w-3xl px-4">
          <div data-layer data-depth="0.8" data-blur className="mb-6 flex flex-col items-center gap-3 text-center">
            <span className="eyebrow">Расписание</span>
            <h2 id="schedule-title" className="font-heading text-3xl font-bold tracking-tight sm:text-4xl">
              Ближайшие занятия
            </h2>
          </div>
          <div data-layer data-depth="1.1">
            <BookableScheduleList
              slots={upcoming}
              isAuthenticated={currentUser !== null}
              classKey={null}
            />
          </div>
          {schedule.length > upcoming.length && (
            <div data-layer data-depth="1.3" className="mt-6 flex justify-center">
              <Link href="/schedule" className={`${GLASS_BUTTON_CLASS} glass-float px-6 py-3 text-sm font-semibold`}>
                Всё расписание →
              </Link>
            </div>
          )}
        </div>
      </Scene>

      {/* Финал: снова тёмная сцена — веер поднимается на своё место из
          hero, кастаньеты ложатся рядом (см. choreography.ts). */}
      <Scene id="contacts" dark labelledBy="contacts-title">
        <div className="mx-auto w-full max-w-6xl px-5 sm:px-6">
          <div className="stage-copy flex max-w-xl flex-col items-start gap-5">
            <div data-layer data-depth="0.8" data-blur className="flex flex-col items-start gap-3">
              <span className="eyebrow">Готовы начать?</span>
              <h2 id="contacts-title" className="font-heading text-3xl font-bold tracking-tight sm:text-4xl">
                Контакты
              </h2>
              <p className="max-w-md text-[var(--text-secondary)]">
                Свяжитесь со студией любым удобным способом — поможем
                выбрать направление и время занятия.
              </p>
            </div>
            <div
              data-layer
              data-depth="1.1"
              className="glass-medium glass-float w-full rounded-[28px] p-6 [text-shadow:none] sm:p-7"
            >
              <dl className="flex flex-col gap-3 text-left">
                <ContactRow label="Адрес" value={CONTACTS.address} />
                <ContactRow label="Телефон" value={CONTACTS.phone} />
              </dl>
              {TELEGRAM_BOT_USERNAME && (
                <a
                  href={`https://t.me/${TELEGRAM_BOT_USERNAME}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={`${PRIMARY_BUTTON_CLASS} mt-5 w-fit gap-2 px-6 py-3 text-base`}
                >
                  Написать в Telegram
                </a>
              )}
            </div>
          </div>
        </div>
      </Scene>
    </HomeStory>
  );
}

// Сцена: section = слой камеры; data-scene-scroll — обёртка, которую
// движок сдвигает по Y в удержании (дрейф и прокрутка высокого контента);
// .scene-inner центрируется, пока помещается, и прижимается к верху, когда
// выше экрана.
function Scene({
  id,
  dark = false,
  labelledBy,
  children,
}: {
  id: string;
  dark?: boolean;
  labelledBy: string;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      data-scene={id}
      aria-labelledby={labelledBy}
      className={dark ? "scene scene--dark stage-dark" : "scene"}
    >
      <div className="scene-scroll" data-scene-scroll>
        <div className="scene-inner">{children}</div>
      </div>
    </section>
  );
}

// Иконки для "Почему мы?" — разные и по теме каждого пункта (группы,
// уровни, расписание). Реальных фото студии/преподавателей в проекте нет,
// выдумывать их нельзя (CLAUDE.md §27). Подложка — маленькая стеклянная
// "линза" того же материала, что и панель вокруг.
function WhyUsIcon({ variant }: { variant: "group" | "levels" | "calendar" }) {
  return (
    <div
      className="glass-subtle flex h-16 w-16 items-center justify-center rounded-2xl text-[var(--primary)]"
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
