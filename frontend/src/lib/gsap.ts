import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

// Регистрируем плагин один раз на модуль (а не в каждом компоненте) —
// повторная регистрация безвредна, но не нужна. Импортируется только из
// клиентских компонентов ("use client"), на сервере этот файл не исполняется.
if (typeof window !== "undefined") {
  gsap.registerPlugin(ScrollTrigger);
}

export { gsap, ScrollTrigger };
