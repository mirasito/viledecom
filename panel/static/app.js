// Фильтры и отметки задач. Отметки хранятся только в этом браузере.
(function () {
  function store(key, val) {
    try { if (val === undefined) return JSON.parse(localStorage.getItem(key) || "{}"); localStorage.setItem(key, JSON.stringify(val)); } catch (e) { return {}; }
  }
  function chips(id, attr, apply) {
    var box = document.getElementById(id); if (!box) return;
    box.addEventListener("click", function (ev) {
      var b = ev.target.closest(".chip"); if (!b) return;
      box.querySelectorAll(".chip").forEach(function (c) { c.classList.toggle("on", c === b); });
      apply(b.getAttribute(attr));
    });
  }
  chips("kind-filter", "data-kind", function (k) {
    document.querySelectorAll("#digests tbody tr").forEach(function (tr) { tr.hidden = k && tr.dataset.kind !== k; });
  });

  var done = store("viled-tasks-done");
  var person = "";
  var hide = document.getElementById("hide-done");
  function refresh() {
    var counts = {};
    document.querySelectorAll(".task").forEach(function (li) {
      var box = li.querySelector("input");
      if (done[li.dataset.id] !== undefined) box.checked = done[li.dataset.id];
      li.classList.toggle("done", box.checked);
      var people = li.dataset.people ? li.dataset.people.split("|") : [];
      if (!box.checked) people.forEach(function (p) { counts[p] = (counts[p] || 0) + 1; });
      if (li.closest("#tasks")) li.hidden = (person && people.indexOf(person) < 0) || (hide && hide.checked && box.checked);
    });
    document.querySelectorAll("[data-count-for]").forEach(function (el) {
      var n = counts[el.dataset.countFor] || 0; el.textContent = n ? n + " открыто" : "";
    });
  }
  document.addEventListener("change", function (ev) {
    var li = ev.target.closest(".task");
    if (li) { done[li.dataset.id] = ev.target.checked; store("viled-tasks-done", done); }
    refresh();
  });
  chips("person-filter", "data-person", function (p) { person = p; refresh(); });
  refresh();
})();
