(() => {
  const form = document.querySelector(".agenda-filters");
  if (!form) return;

  const dateInput = form.querySelector('input[name="data"]');
  const clinicSelect = form.querySelector('select[name="clinica"]');

  document.querySelectorAll("[data-date-step]").forEach((button) => {
    button.addEventListener("click", () => {
      const [year, month, day] = dateInput.value.split("-").map(Number);
      const selected = new Date(year, month - 1, day, 12);
      selected.setDate(selected.getDate() + Number(button.dataset.dateStep));
      const localYear = selected.getFullYear();
      const localMonth = String(selected.getMonth() + 1).padStart(2, "0");
      const localDay = String(selected.getDate()).padStart(2, "0");
      dateInput.value = `${localYear}-${localMonth}-${localDay}`;
      form.requestSubmit();
    });
  });

  dateInput.addEventListener("change", () => form.requestSubmit());
  clinicSelect.addEventListener("change", () => form.requestSubmit());
})();

