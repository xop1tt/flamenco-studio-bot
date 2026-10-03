import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Авторы изображений",
};

// Атрибуция для изображений под CC BY/CC0 (вежливая практика даже там, где
// лицензия её не требует). Источник истины — public/assets/CREDITS.md; при
// замене ассетов обновлять оба.
const CREDITS = [
  {
    use: "Веер на сцене главной",
    title: "Abanico.png",
    href: "https://commons.wikimedia.org/wiki/File:Abanico.png",
    author: "Kbemcap",
    license: "CC0",
    licenseHref: "https://creativecommons.org/publicdomain/zero/1.0/",
  },
  {
    use: "Дымка сцены",
    title: "Incense smoke against a black sky",
    href: "https://commons.wikimedia.org/wiki/File:Incense_smoke_against_a_black_sky_-_Flickr_-_Vanessa_Pike-Russell.jpg",
    author: "Vanessa Pike-Russell",
    license: "CC BY 2.0",
    licenseHref: "https://creativecommons.org/licenses/by/2.0/",
  },
];

export default function CreditsPage() {
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-16">
      <h1 className="font-heading text-3xl font-bold tracking-tight">Авторы изображений</h1>
      <p className="text-[var(--text-secondary)]">
        Фотографии ниже изменены: обрезаны, масштабированы, отделены от фона и тонированы.
        Кастаньеты, роза и лепестки на сцене — рисованные, без фотографической основы.
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
