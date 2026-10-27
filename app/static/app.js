// Comportamentos pequenos da interface: tema claro ou escuro e menu no celular.
// A escolha do tema fica salva só neste navegador.

(function () {
  const raiz = document.documentElement;

  function aplicarTema(tema) {
    raiz.dataset.tema = tema;
    document.querySelectorAll("[data-alternar-tema]").forEach(function (botao) {
      const escuro = tema === "escuro";
      botao.setAttribute("aria-pressed", escuro ? "true" : "false");
      botao.setAttribute("aria-label", escuro ? "Usar tema claro" : "Usar tema escuro");
      botao.title = escuro ? "Usar tema claro" : "Usar tema escuro";
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    aplicarTema(raiz.dataset.tema || "claro");

    document.querySelectorAll("[data-alternar-tema]").forEach(function (botao) {
      botao.addEventListener("click", function () {
        const novo = raiz.dataset.tema === "escuro" ? "claro" : "escuro";
        aplicarTema(novo);
        try { localStorage.setItem("tema", novo); } catch (e) { /* navegador sem armazenamento */ }
      });
    });

    const abrir = document.querySelector("[data-abrir-menu]");
    if (abrir) {
      abrir.addEventListener("click", function () {
        const barra = abrir.closest(".barra");
        const aberta = barra.classList.toggle("aberta");
        abrir.setAttribute("aria-expanded", aberta ? "true" : "false");
      });
    }
  });
})();
