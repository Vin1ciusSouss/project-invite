(() => {
  const pendingKey = "casamento:pending-scroll";
  const positionsKey = "casamento:scroll-positions";
  const read = (key, fallback) => {
    try { return JSON.parse(sessionStorage.getItem(key)) || fallback; }
    catch { return fallback; }
  };
  const write = (key, value) => {
    try { sessionStorage.setItem(key, JSON.stringify(value)); } catch {}
  };
  const savePosition = () => {
    const positions = read(positionsKey, {});
    positions[location.pathname] = { x: scrollX, y: scrollY, at: Date.now() };
    const recent = Object.entries(positions).sort((a, b) => b[1].at - a[1].at).slice(0, 20);
    write(positionsKey, Object.fromEntries(recent));
  };

  // Runs in the head so the new document is shown at its restored position.
  const pending = read(pendingKey, null);
  let restorePosition = null;
  let userInteracted = false;
  ["pointerdown", "wheel", "touchstart", "keydown"].forEach((name) => {
    window.addEventListener(name, () => { userInteracted = true; }, { once: true, passive: true });
  });
  let previousRestoration;
  if (pending) {
    try { sessionStorage.removeItem(pendingKey); } catch {}
    const sameRsvp = pending.target === "/confirmar-presenca" && location.pathname.startsWith("/confirmar-presenca/");
    if (Date.now() - pending.at < 120000) {
      if (location.pathname === pending.target || sameRsvp) restorePosition = pending.destination;
      else if (location.pathname === pending.source) restorePosition = pending.current;
    }
  }
  if (restorePosition) {
    document.documentElement.classList.add("is-restoring-scroll");
    previousRestoration = history.scrollRestoration;
    history.scrollRestoration = "manual";
    if (location.hash) history.replaceState(history.state, "", location.pathname + location.search);
  }

  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (event.defaultPrevented || !(form instanceof HTMLFormElement) || form.method.toLowerCase() !== "post" || !form.dataset.scrollReturn) return;
    savePosition();
    const target = new URL(form.dataset.scrollReturn, location.origin).pathname;
    const current = { x: scrollX, y: scrollY };
    const stored = read(positionsKey, {})[target];
    const destination = target === location.pathname || target.startsWith("/confirmar-presenca")
      ? current : (stored && Date.now() - stored.at < 1800000 ? stored : { x: 0, y: 0 });
    write(pendingKey, { source: location.pathname, target, current, destination, at: Date.now() });
  });
  window.addEventListener("pagehide", savePosition);
  window.addEventListener("pageshow", () => {
    if (restorePosition && !userInteracted) {
      document.documentElement.classList.add("is-restoring-scroll");
      window.scrollTo(restorePosition.x, restorePosition.y);
      document.documentElement.classList.remove("is-restoring-scroll");
    }
  });

  document.addEventListener("DOMContentLoaded", () => {
    if (restorePosition) {
      requestAnimationFrame(() => {
        window.scrollTo(restorePosition.x, restorePosition.y);
        document.documentElement.classList.remove("is-restoring-scroll");
        history.scrollRestoration = previousRestoration || "auto";
      });
    }
    document.querySelectorAll(".flash").forEach((notification) => {
      notification.querySelector(".flash-close")?.addEventListener("click", () => notification.remove());
      if (notification.classList.contains("success")) {
        window.setTimeout(() => notification.remove(), 7000);
      }
    });
  });
})();
