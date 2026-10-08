(() => {
  const body = document.body;
  const backdrop = document.querySelector(".reception-backdrop");
  const recordDrawer = document.querySelector(".record-drawer");
  const formDrawer = document.querySelector(".form-drawer");
  const records = JSON.parse(document.querySelector("#reception-records").textContent);
  const recordMap = new Map(records.map((record) => [String(record.id), record]));
  let lastTrigger = null;

  function closeDrawers({ restoreFocus = true } = {}) {
    [recordDrawer, formDrawer].forEach((drawer) => {
      drawer.classList.remove("is-open");
      drawer.setAttribute("aria-hidden", "true");
    });
    backdrop.hidden = true;
    body.classList.remove("drawer-open");
    if (restoreFocus) lastTrigger?.focus();
  }

  function openDrawer(drawer, trigger = null) {
    closeDrawers({ restoreFocus: false });
    lastTrigger = trigger;
    backdrop.hidden = false;
    drawer.classList.add("is-open");
    drawer.setAttribute("aria-hidden", "false");
    body.classList.add("drawer-open");
    drawer.querySelector(".operation-drawer__close").focus();
  }

  document.querySelectorAll("[data-close-drawer]").forEach((button) => {
    button.addEventListener("click", () => closeDrawers());
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && body.classList.contains("drawer-open")) {
      closeDrawers();
    }
  });

  function setField(name, value) {
    const target = recordDrawer.querySelector(`[data-record-field="${name}"]`);
    if (target) target.textContent = value;
  }

  function renderEvents(events) {
    const container = recordDrawer.querySelector(".operational-timeline__items");
    container.replaceChildren();
    if (!events.length) {
      const empty = document.createElement("p");
      empty.className = "timeline-empty";
      empty.textContent = "Nenhum evento operacional registrado.";
      container.append(empty);
      return;
    }
    events.forEach((event) => {
      const article = document.createElement("article");
      article.className = "timeline-event";

      const dot = document.createElement("span");
      dot.className = "timeline-event__dot";
      dot.setAttribute("aria-hidden", "true");

      const time = document.createElement("time");
      time.textContent = `${event.date} · ${event.time}`;

      const content = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = event.label;
      content.append(title);
      if (event.simulated) {
        const badge = document.createElement("span");
        badge.className = "simulated-badge";
        badge.textContent = "SIMULADO";
        content.append(badge);
      }
      const detail = document.createElement("p");
      detail.textContent = event.detail;
      content.append(detail);
      article.append(dot, time, content);
      container.append(article);
    });
  }

  function showRecord(id, trigger = null) {
    const record = recordMap.get(String(id));
    if (!record) return;
    setField("patient", record.patient);
    setField("phone", record.phone);
    setField("doctor", record.doctor);
    setField("doctor_registration", record.doctor_registration);
    setField("clinic", record.clinic);
    setField("scheduled_date", record.scheduled_date);
    setField("scheduled_time", record.scheduled_time);
    setField("appointment_type", record.appointment_type);
    setField("contact_lead", record.contact_lead);
    setField("status", record.status);
    recordDrawer.querySelector(".record-avatar").textContent = record.patient.slice(0, 1);
    const status = recordDrawer.querySelector(".record-status");
    status.className = `record-status record-status--${record.status_css}`;
    renderEvents(record.events);
    openDrawer(recordDrawer, trigger);
  }

  document.querySelectorAll(".js-open-record").forEach((button) => {
    button.addEventListener("click", () => showRecord(button.dataset.recordId, button));
  });
  document.querySelector(".js-open-form").addEventListener("click", (event) => {
    openDrawer(formDrawer, event.currentTarget);
  });

  const doctorClinicMap = JSON.parse(document.querySelector("#doctor-clinic-map").textContent);
  const doctorSelect = formDrawer.querySelector('[name="doctor"]');
  const clinicSelect = formDrawer.querySelector('[name="clinic"]');
  function filterFormClinics() {
    const allowed = new Set(doctorClinicMap[doctorSelect.value] || []);
    [...clinicSelect.options].forEach((option) => {
      if (!option.value) return;
      option.disabled = Boolean(doctorSelect.value) && !allowed.has(Number(option.value));
    });
  }
  doctorSelect.addEventListener("change", filterFormClinics);
  filterFormClinics();

  const phoneInput = formDrawer.querySelector('[name="phone"]');
  phoneInput.addEventListener("input", () => {
    const digits = phoneInput.value.replace(/\D/g, "").slice(0, 11);
    if (digits.length <= 2) {
      phoneInput.value = digits;
    } else if (digits.length <= 6) {
      phoneInput.value = `(${digits.slice(0, 2)}) ${digits.slice(2)}`;
    } else if (digits.length <= 10) {
      phoneInput.value = `(${digits.slice(0, 2)}) ${digits.slice(2, 6)}-${digits.slice(6)}`;
    } else {
      phoneInput.value = `(${digits.slice(0, 2)}) ${digits.slice(2, 7)}-${digits.slice(7)}`;
    }
  });

  const filters = document.querySelector(".reception-filters");
  filters.querySelectorAll('input[type="date"], select').forEach((control) => {
    control.addEventListener("change", () => filters.requestSubmit());
  });

  if (body.dataset.openForm === "true") {
    openDrawer(formDrawer);
    const firstError = formDrawer.querySelector(".reception-field--error input, .reception-field--error select");
    firstError?.focus();
  } else if (body.dataset.selectedRecord) {
    showRecord(body.dataset.selectedRecord);
  }
})();

