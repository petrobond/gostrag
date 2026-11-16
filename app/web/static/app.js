document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("form").forEach((form) => {
    if (form.hasAttribute("hx-post") || form.hasAttribute("hx-delete")) return;
    form.addEventListener("submit", () => {
      const button = form.querySelector('button[type="submit"]');
      if (!button) return;
      button.disabled = true;
      button.classList.add("is-loading");
    });
  });

  const scrollThread = () => {
    document.querySelectorAll("[data-scroll-bottom]").forEach((element) => {
      element.scrollTop = element.scrollHeight;
    });
  };

  scrollThread();
  document.body.addEventListener("htmx:afterSwap", scrollThread);
  document.body.addEventListener("htmx:afterSettle", scrollThread);
});
