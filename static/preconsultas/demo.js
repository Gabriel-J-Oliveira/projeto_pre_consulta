(() => {
  const body = document.body;
  const getCsrf = () => document.querySelector('[name="csrfmiddlewaretoken"]')?.value || "";
  const sleep = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms));

  const toast = document.querySelector(".toast");
  let toastTimer;
  function showToast(message, isError = false) {
    window.clearTimeout(toastTimer);
    toast.querySelector("p").textContent = message;
    toast.querySelector(".toast__icon").textContent = isError ? "!" : "✓";
    toast.style.borderColor = isError ? "#e7b8b1" : "";
    toast.style.background = isError ? "#fff3f1" : "";
    toast.hidden = false;
    toastTimer = window.setTimeout(() => { toast.hidden = true; }, 4600);
  }

  function firstError(payload) {
    const groups = Object.values(payload.errors || {});
    return groups[0]?.[0]?.message || "Não foi possível concluir a ação.";
  }

  async function postForm(url, formData) {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "X-CSRFToken": getCsrf(),
        "X-Requested-With": "XMLHttpRequest",
      },
      body: formData,
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) throw new Error(firstError(payload));
    return payload;
  }

  // Tabs preserve the summary while switching only the right-hand source panel.
  const tabs = [...document.querySelectorAll("[data-tab]")];
  function activateTab(name, moveFocus = false) {
    tabs.forEach((tab) => {
      const active = tab.dataset.tab === name;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", String(active));
      tab.setAttribute("tabindex", active ? "0" : "-1");
      document.querySelector(`#panel-${tab.dataset.tab}`).hidden = !active;
      if (active && moveFocus) tab.focus();
    });
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => activateTab(tab.dataset.tab));
    tab.addEventListener("keydown", (event) => {
      if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
      event.preventDefault();
      const direction = event.key === 'ArrowRight' ? 1 : -1;
      const next = tabs[(index + direction + tabs.length) % tabs.length];
      activateTab(next.dataset.tab, true);
    });
  });

  document.querySelectorAll(".js-view-source").forEach((button) => {
    button.addEventListener("click", () => {
      activateTab("conversation");
      const target = document.querySelector(`[data-source-item="${button.dataset.source}"]`);
      if (!target) return;
      document.querySelectorAll(".message.is-highlighted").forEach((item) => item.classList.remove("is-highlighted"));
      target.classList.add("is-highlighted");
      target.scrollIntoView({ behavior: "smooth", block: "center" });
      target.focus({ preventScroll: true });
      window.setTimeout(() => target.classList.remove("is-highlighted"), 3200);
    });
  });

  // In-page PDF drawer with explicit loading and missing-file states.
  const drawer = document.querySelector(".attachment-drawer");
  const backdrop = document.querySelector(".drawer-backdrop");
  const loading = drawer.querySelector(".viewer-loading");
  const empty = drawer.querySelector(".viewer-empty");
  const iframe = drawer.querySelector(".pdf-viewer");
  let drawerTrigger = null;

  function closeDrawer() {
    drawer.classList.remove("is-open");
    drawer.setAttribute("aria-hidden", "true");
    backdrop.hidden = true;
    body.classList.remove("drawer-open");
    iframe.src = "about:blank";
    drawerTrigger?.focus();
  }

  async function openDrawer(button) {
    drawerTrigger = button;
    drawer.querySelector("#drawer-title").textContent = "Carregando documento";
    loading.hidden = false;
    empty.hidden = true;
    iframe.hidden = true;
    backdrop.hidden = false;
    drawer.classList.add("is-open");
    drawer.setAttribute("aria-hidden", "false");
    body.classList.add("drawer-open");
    drawer.querySelector(".drawer-close").focus();

    try {
      const [response] = await Promise.all([fetch(button.dataset.statusUrl), sleep(320)]);
      if (!response.ok) throw new Error("Não foi possível consultar o arquivo.");
      const payload = await response.json();
      drawer.querySelector("#drawer-title").textContent = payload.filename || "Documento";
      loading.hidden = true;
      if (payload.available) {
        iframe.src = payload.url;
        iframe.hidden = false;
      } else {
        empty.querySelector(".viewer-message").textContent = payload.message;
        empty.querySelector(".viewer-filename").textContent = payload.filename;
        empty.hidden = false;
      }
    } catch (error) {
      loading.hidden = true;
      empty.querySelector(".viewer-message").textContent = error.message;
      empty.querySelector(".viewer-filename").textContent = "Tente novamente em instantes.";
      empty.hidden = false;
    }
  }

  document.querySelectorAll(".js-open-attachment").forEach((button) => {
    button.addEventListener("click", () => openDrawer(button));
  });
  document.querySelectorAll("[data-drawer-close]").forEach((button) => button.addEventListener("click", closeDrawer));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && drawer.classList.contains("is-open")) closeDrawer();
  });

  // Corrections are overlays: the original SummaryItem and its sources never change.
  const dialog = document.querySelector(".correction-dialog");
  const correctionForm = dialog.querySelector(".correction-form");
  const itemIdField = correctionForm.querySelector('[name="summary_item_id"]');
  const actionField = correctionForm.querySelector('[name="action"]');
  const newValueField = correctionForm.querySelector('[name="new_value"]');
  let correctionTrigger = null;

  function closeDialog() {
    dialog.close();
    correctionTrigger?.focus();
  }

  document.querySelectorAll(".js-open-correction").forEach((button) => {
    button.addEventListener("click", () => {
      correctionTrigger = button;
      const current = button.dataset.currentValue;
      itemIdField.value = button.dataset.itemId;
      actionField.value = "update";
      newValueField.value = current;
      correctionForm.querySelector(".comparison__old").textContent = current;
      dialog.querySelector("#correction-title").textContent = button.dataset.itemLabel;
      dialog.showModal();
      newValueField.focus();
      newValueField.select();
    });
  });

  dialog.querySelector(".dialog-close").addEventListener("click", closeDialog);
  dialog.querySelector(".dialog-cancel").addEventListener("click", closeDialog);

  async function submitCorrection(action) {
    actionField.value = action;
    const formData = new FormData(correctionForm);
    if (action === "hide") formData.set("new_value", "");
    try {
      const payload = await postForm(body.dataset.correctionUrl, formData);
      const item = document.querySelector(`[data-summary-item="${payload.item_id}"]`);
      if (payload.action === "hide") {
        item?.classList.add("is-removing");
        window.setTimeout(() => item?.remove(), 220);
      } else if (item) {
        item.querySelector(".summary-item__value").textContent = payload.new_value;
        const badge = item.querySelector(".source-type");
        badge.className = "source-type source-type--doctor";
        badge.textContent = "Ajustado pelo médico";
        const edit = item.querySelector(".js-open-correction");
        edit.dataset.currentValue = payload.new_value;
      }
      closeDialog();
      showToast(payload.message);
    } catch (error) {
      showToast(error.message, true);
    }
  }

  correctionForm.addEventListener("submit", (event) => {
    event.preventDefault();
    submitCorrection("update");
  });
  dialog.querySelector(".js-hide-item").addEventListener("click", () => submitCorrection("hide"));

  // Notes and lightweight feedback are saved asynchronously with CSRF protection.
  document.querySelectorAll(".js-async-form").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const submit = form.querySelector('[type="submit"]');
      submit.disabled = true;
      try {
        const payload = await postForm(form.action, new FormData(form));
        form.reset();
        showToast(payload.message);
      } catch (error) {
        showToast(error.message, true);
      } finally {
        submit.disabled = false;
      }
    });
  });

  document.querySelectorAll(".js-feedback").forEach((button) => {
    button.addEventListener("click", async () => {
      const formData = new FormData();
      formData.set("kind", button.dataset.kind);
      try {
        const payload = await postForm(body.dataset.feedbackUrl, formData);
        document.querySelectorAll(".js-feedback").forEach((item) => item.classList.remove("is-selected"));
        button.classList.add("is-selected");
        showToast(payload.message);
      } catch (error) {
        showToast(error.message, true);
      }
    });
  });
})();

