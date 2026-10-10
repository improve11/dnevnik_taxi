const $ = (selector) => document.querySelector(selector);
const datePicker = $("#date-picker");
const modal = $("#modal");
const form = $("#trip-form");
const errorBanner = $("#error-banner");
const successBanner = $("#success-banner");
const formError = $("#form-error");
const submitButton = $("#submit-trip");

const money = (value) => new Intl.NumberFormat("ru-RU", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 2
}).format(value);

const localDateString = (date) => {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
};

function showNotice(element, message) {
  element.textContent = message;
  element.classList.remove("hidden");
}
function clearNotices() {
  errorBanner.classList.add("hidden");
  successBanner.classList.add("hidden");
}
function pluralTrips(count) {
  const mod10 = count % 10, mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return `${count} поездка`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${count} поездки`;
  return `${count} поездок`;
}
function formatTime(value) {
  return new Intl.DateTimeFormat("ru-RU", { hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}
function formatDuration(start, end) {
  const minutes = Math.max(0, Math.round((new Date(end) - new Date(start)) / 60000));
  return `${minutes} мин`;
}
function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[char]);
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.detail;
    let message = typeof detail === "string" ? detail :
      Array.isArray(detail) ? detail.map((item) => item.msg).join("; ") :
      `Ошибка сервера (${response.status})`;
    throw new Error(message || `Ошибка сервера (${response.status})`);
  }
  return payload;
}

async function loadDay() {
  clearNotices();
  const day = datePicker.value;
  if (!day) return;
  $("#date-heading").textContent = new Date(`${day}T12:00:00`).toLocaleDateString("ru-RU", {
    day: "numeric", month: "long", year: "numeric"
  });
  $("#trips-body").innerHTML = '<tr><td colspan="5" class="empty-cell">Загрузка поездок…</td></tr>';
  try {
    const [summary, trips] = await Promise.all([
      fetchJson(`/api/summary?date=${encodeURIComponent(day)}`),
      fetchJson(`/api/trips?date=${encodeURIComponent(day)}`)
    ]);
    $("#revenue").textContent = money(summary.revenue);
    $("#take-home").textContent = money(summary.take_home);
    $("#commission").textContent = money(summary.commission);
    $("#trip-count").textContent = summary.trip_count;
    $("#cash-amount").textContent = money(summary.cash.amount);
    $("#cash-count").textContent = pluralTrips(summary.cash.trip_count);
    $("#card-amount").textContent = money(summary.card.amount);
    $("#card-count").textContent = pluralTrips(summary.card.trip_count);
    $("#list-count").textContent = summary.trip_count;

    if (!trips.length) {
      $("#trips-body").innerHTML = '<tr><td colspan="5" class="empty-cell">За этот день поездок нет. Добавьте первую запись.</td></tr>';
      return;
    }
    $("#trips-body").innerHTML = trips.map((trip) => {
      const isCash = trip.payment === "cash";
      const payment = isCash ? "Наличные" : "Карта";
      return `<tr>
        <td><strong>${escapeHtml(payment)} поездка</strong><div class="trip-id">ID: ${escapeHtml(trip.id)}</div></td>
        <td class="time-cell">${formatTime(trip.start)} – ${formatTime(trip.end)}<div class="trip-id">${formatDuration(trip.start, trip.end)}</div></td>
        <td><span class="payment-badge ${isCash ? "cash" : ""}">${isCash ? "●" : "▤"} ${payment}</span></td>
        <td>${money(trip.commission)}</td>
        <td class="align-right amount-cell">${money(trip.amount)}</td>
      </tr>`;
    }).join("");
  } catch (error) {
    $("#trips-body").innerHTML = '<tr><td colspan="5" class="empty-cell">Не удалось загрузить данные.</td></tr>';
    showNotice(errorBanner, `Ошибка загрузки: ${error.message}`);
  }
}

function shiftDay(amount) {
  const current = new Date(`${datePicker.value}T12:00:00`);
  current.setDate(current.getDate() + amount);
  datePicker.value = localDateString(current);
  loadDay();
}

function openModal() {
  form.reset();
  formError.classList.add("hidden");
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60000;
  const localNow = new Date(now.getTime() - offset).toISOString().slice(0, 16);
  const startInput = form.elements.start;
  const endInput = form.elements.end;
  startInput.value = localNow;
  const end = new Date(new Date(localNow).getTime() + 20 * 60000);
  endInput.value = `${localDateString(end)}T${String(end.getHours()).padStart(2, "0")}:${String(end.getMinutes()).padStart(2, "0")}`;
  modal.classList.remove("hidden");
}
function closeModal() { modal.classList.add("hidden"); }

function withTimezone(localDateTime) {
  const parsed = new Date(localDateTime);
  const offsetMinutes = -parsed.getTimezoneOffset();
  const sign = offsetMinutes >= 0 ? "+" : "-";
  const absolute = Math.abs(offsetMinutes);
  const offset = `${sign}${String(Math.floor(absolute / 60)).padStart(2, "0")}:${String(absolute % 60).padStart(2, "0")}`;
  return `${localDateTime}:00${offset}`;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  formError.classList.add("hidden");
  submitButton.disabled = true;
  submitButton.textContent = "Сохраняем…";
  const data = new FormData(form);
  const start = data.get("start");
  const end = data.get("end");
  const amount = Number(data.get("amount"));
  const commission = Number(data.get("commission"));

  if (amount <= 0) {
    formError.textContent = "Сумма должна быть больше нуля.";
    formError.classList.remove("hidden");
    submitButton.disabled = false;
    submitButton.textContent = "Сохранить поездку";
    return;
  }
  if (new Date(end) <= new Date(start)) {
    formError.textContent = "Время окончания должно быть позже времени начала.";
    formError.classList.remove("hidden");
    submitButton.disabled = false;
    submitButton.textContent = "Сохранить поездку";
    return;
  }
  if (commission < 0 || commission > amount) {
    formError.textContent = "Комиссия должна быть от 0 до суммы поездки.";
    formError.classList.remove("hidden");
    submitButton.disabled = false;
    submitButton.textContent = "Сохранить поездку";
    return;
  }

  const payload = {
    id: String(data.get("id")).trim(),
    start: withTimezone(start),
    end: withTimezone(end),
    amount,
    commission,
    payment: data.get("payment")
  };
  try {
    await fetchJson("/api/trips", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    closeModal();
    datePicker.value = start.slice(0, 10);
    await loadDay();
    showNotice(successBanner, "Поездка сохранена.");
  } catch (error) {
    formError.textContent = error.message;
    formError.classList.remove("hidden");
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Сохранить поездку";
  }
});

$("#prev-day").addEventListener("click", () => shiftDay(-1));
$("#next-day").addEventListener("click", () => shiftDay(1));
$("#today-button").addEventListener("click", () => {
  datePicker.value = localDateString(new Date());
  loadDay();
});
datePicker.addEventListener("change", loadDay);
$("#open-form").addEventListener("click", openModal);
$("#close-form").addEventListener("click", closeModal);
$("#cancel-form").addEventListener("click", closeModal);
modal.addEventListener("click", (event) => {
  if (event.target.dataset.close === "true") closeModal();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeModal();
});

datePicker.value = localDateString(new Date());
loadDay();
