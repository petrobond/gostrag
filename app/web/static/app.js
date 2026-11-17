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

  const palette = document.querySelector("[data-command-palette]");
  const paletteSearch = document.querySelector("[data-command-search]");
  const paletteItems = () => Array.from(document.querySelectorAll("[data-command-item]"));

  const filterPalette = () => {
    const needle = (paletteSearch?.value || "").trim().toLowerCase();
    paletteItems().forEach((item) => {
      const haystack = `${item.dataset.commandName} ${item.dataset.commandDesc}`.toLowerCase();
      item.hidden = Boolean(needle) && !haystack.includes(needle);
    });
  };

  const openPalette = () => {
    if (!palette) return;
    palette.hidden = false;
    if (paletteSearch) {
      paletteSearch.value = "";
      filterPalette();
      paletteSearch.focus();
    }
  };

  const closePalette = () => {
    if (palette) palette.hidden = true;
  };

  document.querySelectorAll("[data-command-open]").forEach((button) => {
    button.addEventListener("click", openPalette);
  });
  document.querySelectorAll("[data-command-close]").forEach((button) => {
    button.addEventListener("click", closePalette);
  });
  if (palette) {
    palette.addEventListener("click", (event) => {
      if (event.target === palette) closePalette();
    });
    paletteSearch?.addEventListener("input", filterPalette);
  }

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && palette && !palette.hidden) {
      closePalette();
      return;
    }
    if (event.key !== "/" || event.metaKey || event.ctrlKey || event.altKey) return;
    const target = event.target;
    if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) {
      if (target.tagName === "TEXTAREA" && !target.value && palette?.hidden) {
        event.preventDefault();
        openPalette();
      }
      return;
    }
    if (palette?.hidden) {
      event.preventDefault();
      openPalette();
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
