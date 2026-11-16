document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("form").forEach((form) => {
    form.addEventListener("submit", () => {
      const button = form.querySelector('button[type="submit"]');
      if (!button) return;
      button.disabled = true;
      button.classList.add("is-loading");
    });
  });

  const thread = document.querySelector("[data-scroll-bottom]");
  if (thread) thread.scrollTop = thread.scrollHeight;
});
