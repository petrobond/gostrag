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

  document.addEventListener("keydown", (event) => {
    const textarea = event.target.closest?.("textarea[data-enter-submit]");
    if (!textarea) return;
    if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
    if (event.keyCode === 229) return;
    const form = textarea.closest("form");
    if (!form) return;
    const submitButton = form.querySelector('button[type="submit"]');
    if (submitButton && submitButton.disabled) return;
    event.preventDefault();
    if (typeof form.requestSubmit === "function") {
      form.requestSubmit();
    } else {
      form.submit();
    }
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
