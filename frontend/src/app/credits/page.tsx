import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Авторы изображений",
};

// Атрибуция для сторонних изображений под CC BY/CC0 (вежливая практика даже
// там, где лицензия её не требует). Источник истины —
// public/assets/CREDITS.md; при замене ассетов обновлять оба. Сейчас
// сторонних изображений на сайте нет: веер и кастаньеты на главной
// нарисованы для проекта.
const CREDITS: {
  use: string;
  title: string;
  href: string;
  author: string;
  license: string;
  licenseHref: string;
}[] = [];

export default function CreditsPage() {
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-16">
      <h1 className="font-heading text-3xl font-bold tracking-tight">Авторы изображений</h1>
      <p className="text-[var(--text-secondary)]">
        Веер и кастаньеты на сцене главной нарисованы для этого сайта, без
        фотографической основы.
        {CREDITS.length === 0 && " Сторонних изображений на сайте сейчас нет."}
      </p>
      <ul className="flex flex-col gap-3">
        {CREDITS.map((credit) => (
          <li key={credit.href} className="glass-medium rounded-2xl p-5">
            <div className="text-sm text-[var(--text-secondary)]">{credit.use}</div>
            <a className="font-medium underline" href={credit.href} target="_blank" rel="noopener noreferrer">
              «{credit.title}»
            </a>{" "}
            — {credit.author},{" "}
            <a className="underline" href={credit.licenseHref} target="_blank" rel="noopener noreferrer">
              {credit.license}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
