const quotaTemplate = () => document.getElementById("quota-row-template");

const bindQuotaEditors = () => {
  document.querySelectorAll("[data-quota-editor]").forEach((editor) => {
    const rows = editor.querySelector("[data-quota-rows]");
    const addButton = editor.querySelector("[data-add-quota-row]");
    if (!rows || !addButton) {
      return;
    }

    addButton.addEventListener("click", () => {
      const template = quotaTemplate();
      if (!template) {
        return;
      }
      rows.appendChild(template.content.cloneNode(true));
    });

    rows.addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement) || !target.matches("[data-remove-quota-row]")) {
        return;
      }

      const row = target.closest(".quota-row");
      if (!row) {
        return;
      }

      const rowCount = rows.querySelectorAll(".quota-row").length;
      if (rowCount === 1) {
        row.querySelectorAll("input").forEach((input) => {
          input.value = "";
        });
        const select = row.querySelector("select");
        if (select) {
          select.value = "auto";
        }
        return;
      }

      row.remove();
    });
  });
};

const bindUserFilter = () => {
  const filter = document.querySelector("[data-user-filter]");
  const table = document.querySelector("[data-user-table]");
  if (!(filter instanceof HTMLInputElement) || !(table instanceof HTMLElement)) {
    return;
  }

  filter.addEventListener("input", () => {
    const term = filter.value.trim().toLowerCase();
    table.querySelectorAll("[data-user-row]").forEach((row) => {
      if (!(row instanceof HTMLElement)) {
        return;
      }
      const visible = row.textContent.toLowerCase().includes(term);
      row.hidden = !visible;
    });
  });
};

const bindCopyButtons = () => {
  document.querySelectorAll("[data-copy-text]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!(button instanceof HTMLElement)) {
        return;
      }
      const text = button.getAttribute("data-copy-text") || "";
      await navigator.clipboard.writeText(text);
      const previous = button.textContent;
      button.textContent = "Copied";
      window.setTimeout(() => {
        button.textContent = previous;
      }, 1200);
    });
  });
};

window.addEventListener("DOMContentLoaded", () => {
  bindQuotaEditors();
  bindUserFilter();
  bindCopyButtons();
});
