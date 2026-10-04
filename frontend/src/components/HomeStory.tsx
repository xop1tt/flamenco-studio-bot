"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { startSceneEngine, startStaticScenes } from "@/components/home/sceneEngine";

export type SceneLink = { id: string; label: string };

/**
 * Каркас главной как последовательности полноэкранных сцен.
 *
 *   .scenes            трек прокрутки; в живом режиме его высоту задаёт
 *                      движок (сумма длительностей переходов и удержаний)
 *     .scenes-viewport sticky-"камера" высотой в экран
 *       stage          фон + реквизит (HomeStage, серверный)
 *       .scenes-layer  сцены (children) — слои поверх фона
 *       .scene-nav     точки-сцены (только десктоп, только живой режим)
 *
 * Без JS и при prefers-reduced-motion сцены — обычные блоки в потоке
 * страницы (globals.css, .scenes:not([data-live])), всё читается и
 * кликается как раньше. Живой режим включает sceneEngine.
 */
export function HomeStory({
  stage,
  scenes,
  children,
}: {
  stage: ReactNode;
  scenes: SceneLink[];
  children: ReactNode;
}) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const navRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    const start = () =>
      reduced.matches ? startStaticScenes(root) : startSceneEngine(root, navRef.current);

    let stop = start();
    const onChange = () => {
      stop();
      stop = start();
    };
    reduced.addEventListener("change", onChange);
    return () => {
      reduced.removeEventListener("change", onChange);
      stop();
    };
  }, []);

  return (
    <div ref={rootRef} className="scenes">
      <div className="scenes-viewport" data-viewport>
        {stage}
        <div className="scenes-layer">{children}</div>
        <nav ref={navRef} className="scene-nav glass-subtle glass-float" aria-label="Сцены главной">
          {scenes.map((scene, i) => (
            <button
              key={scene.id}
              type="button"
              data-scene-nav={i}
              className="scene-nav-dot"
              aria-label={scene.label}
            >
              <span className="scene-nav-mark" aria-hidden="true" />
              <span className="scene-nav-label" aria-hidden="true">
                {scene.label}
              </span>
            </button>
          ))}
        </nav>
      </div>
    </div>
  );
}
