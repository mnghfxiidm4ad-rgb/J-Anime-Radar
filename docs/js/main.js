(function () {
  const nav = document.querySelector("[data-nav]");
  const toggle = document.querySelector("[data-nav-toggle]");
  if (toggle && nav) {
    toggle.addEventListener("click", function () {
      nav.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", nav.classList.contains("is-open") ? "true" : "false");
    });
  }

  const chips = Array.from(document.querySelectorAll("[data-genre]"));
  const cards = Array.from(document.querySelectorAll("[data-card]"));
  const search = document.querySelector("[data-search]");

  function applyFilters() {
    const active = chips.find(function (c) { return c.classList.contains("is-on"); });
    const genre = active ? active.getAttribute("data-genre") : "all";
    const q = (search && search.value ? search.value : "").trim().toLowerCase();
    let visible = 0;
    cards.forEach(function (card) {
      const g = (card.getAttribute("data-genres") || "").toLowerCase();
      const t = (card.getAttribute("data-title") || "").toLowerCase();
      const okGenre = genre === "all" || g.indexOf(genre.toLowerCase()) !== -1;
      const okSearch = !q || t.indexOf(q) !== -1 || g.indexOf(q) !== -1;
      const show = okGenre && okSearch;
      card.style.display = show ? "" : "none";
      if (show) visible += 1;
    });
    const empty = document.querySelector("[data-empty]");
    if (empty) empty.hidden = visible !== 0;
  }

  chips.forEach(function (chip) {
    chip.addEventListener("click", function () {
      chips.forEach(function (c) { c.classList.remove("is-on"); });
      chip.classList.add("is-on");
      applyFilters();
    });
  });
  if (search) search.addEventListener("input", applyFilters);
})();
