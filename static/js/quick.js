(function () {
  const root = document.getElementById("quick-app");
  if (!root || root.dataset.saved === "1") return;

  const form = document.getElementById("quick-form");
  const panels = Array.from(form.querySelectorAll(".panel[data-step]"));
  const stepLabel = document.getElementById("step-label");
  const weightInput = document.getElementById("input-weight");
  const fatInput = document.getElementById("input-fat");
  const muscleInput = document.getElementById("input-muscle");
  const dateInput = document.getElementById("input-date");
  const weightError = document.getElementById("error-weight");

  let step = 1;

  function normalizeNumber(raw) {
    return String(raw || "")
      .trim()
      .replace(",", ".");
  }

  function isValidNumber(raw, { required = false } = {}) {
    const value = normalizeNumber(raw);
    if (!value) return !required;
    if (!/^\d+(\.\d+)?$/.test(value)) return false;
    return Number(value) > 0;
  }

  function showStep(next) {
    step = next;
    panels.forEach((panel) => {
      const active = Number(panel.dataset.step) === step;
      panel.hidden = !active;
      panel.classList.toggle("is-active", active);
    });
    stepLabel.textContent = `${step} / 5`;
    const focusMap = {
      1: weightInput,
      2: fatInput,
      3: muscleInput,
      4: dateInput,
    };
    const el = focusMap[step];
    if (el) {
      requestAnimationFrame(() => {
        el.focus();
        if (el.select) el.select();
      });
    }
    if (step === 5) updateReview();
  }

  function updateReview() {
    const weight = normalizeNumber(weightInput.value);
    const fat = normalizeNumber(fatInput.value);
    const muscle = normalizeNumber(muscleInput.value);
    const measuredOn = dateInput.value || root.dataset.today;
    document.getElementById("review-weight").textContent = weight ? `${weight} kg` : "—";
    document.getElementById("review-fat").textContent = fat ? `${fat}%` : "—";
    document.getElementById("review-muscle").textContent = muscle ? `${muscle}%` : "—";
    document.getElementById("review-date").textContent = measuredOn || "—";
  }

  function syncHidden() {
    document.getElementById("field-weight").value = normalizeNumber(weightInput.value);
    document.getElementById("field-fat").value = normalizeNumber(fatInput.value);
    document.getElementById("field-muscle").value = normalizeNumber(muscleInput.value);
    document.getElementById("field-date").value = dateInput.value || root.dataset.today;
  }

  function goNext() {
    if (step === 1) {
      if (!isValidNumber(weightInput.value, { required: true })) {
        weightError.hidden = false;
        weightError.textContent = "Enter a weight greater than zero.";
        weightInput.focus();
        return;
      }
      weightError.hidden = true;
    }
    if (step === 2 && fatInput.value && !isValidNumber(fatInput.value)) {
      fatInput.focus();
      return;
    }
    if (step === 3 && muscleInput.value && !isValidNumber(muscleInput.value)) {
      muscleInput.focus();
      return;
    }
    if (step < 5) showStep(step + 1);
  }

  function goBack() {
    if (step > 1) showStep(step - 1);
  }

  function skipOptional() {
    if (step === 2) {
      fatInput.value = "";
      showStep(3);
      return;
    }
    if (step === 3) {
      muscleInput.value = "";
      showStep(4);
    }
  }

  form.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    if (target.matches("[data-next]")) {
      event.preventDefault();
      goNext();
    } else if (target.matches("[data-back]")) {
      event.preventDefault();
      goBack();
    } else if (target.matches("[data-skip]")) {
      event.preventDefault();
      skipOptional();
    }
  });

  form.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    if (target.id === "input-date") return;
    if (step < 5) {
      event.preventDefault();
      goNext();
    }
  });

  form.addEventListener("submit", () => {
    syncHidden();
    const btn = document.getElementById("save-btn");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Saving…";
    }
  });

  // If server returned an error, jump to review with values preserved is hard
  // without repost; start at weight for a clean flow.
  showStep(root.dataset.error ? 5 : 1);
})();
