const API_BASE = "";

let authToken = localStorage.getItem("token");
let currentUser = JSON.parse(localStorage.getItem("user") || "null");
let searchResults = [];
let pending = null;   // journey being booked: {option, className, count, passengers}

const $ = (id) => document.getElementById(id);
const rupee = (n) => "₹" + Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 0, maximumFractionDigits: 2 });

/* API HELPER */

async function api(path, options = {}) {
    const headers = {
        "Content-Type": "application/json",
        ...(options.headers || {})
    };

    if (authToken) {
        headers.Authorization = `Bearer ${authToken}`;
    }

    const response = await fetch(API_BASE + path, {
        ...options,
        headers
    });

    const raw = await response.text();
    let data = {};

    try {
        data = raw ? JSON.parse(raw) : {};
    } catch {
        data = { detail: raw };
    }

    if (!response.ok) {
        let message = data.detail || data.message || "Request failed.";

        if (Array.isArray(message)) {
            message = message.map(item => item.msg || "Invalid input").join(", ");
        }

        if (response.status === 401 && authToken) {
            // stale/invalid token: clear it so the user logs in again
            authToken = null;
            currentUser = null;
            localStorage.removeItem("token");
            localStorage.removeItem("user");
        }

        throw new Error(message);
    }

    return data;
}

/* NOTIFICATIONS */

function showNotice(id, message, type = "error") {
    const element = $(id);

    if (!element) {
        toast(message);
        return;
    }

    element.textContent = message;
    element.className = "notice " + type;
}

function clearNotice(id) {
    const element = $(id);

    if (element) {
        element.textContent = "";
        element.className = "";
    }
}

function toast(message) {
    const element = $("toast");

    if (!element) {
        alert(message);
        return;
    }

    element.textContent = message;
    element.classList.remove("hidden");

    setTimeout(() => element.classList.add("hidden"), 3000);
}

/* NAVIGATION */

function showPage(name) {
    document.querySelectorAll(".page").forEach(page => {
        page.classList.add("hidden");
    });

    const page = $("page-" + name);
    if (page) page.classList.remove("hidden");

    const labels = {
        home: "Dashboard",
        search: "Find a Journey",
        bookings: "My Bookings",
        status: "Train Status",
        login: "Login",
        register: "Create Account",
        passengers: "Passenger Details",
        payment: "Payment",
        confirmation: "Booking Confirmation",
        forgot: "Forgot Password",
        reset: "Reset Password"
    };

    if ($("crumb")) {
        $("crumb").textContent = labels[name] || name;
    }

    document.querySelectorAll("[data-page]").forEach(button => {
        button.classList.toggle("active", button.dataset.page === name);
    });

    if (name === "bookings") loadBookings();
}

/* AUTHENTICATION */

function setAuth(data) {
    authToken = data.access_token || data.token;
    currentUser = data.user || data;

    if (authToken) {
        localStorage.setItem("token", authToken);
    }

    localStorage.setItem("user", JSON.stringify(currentUser));
    updateProfile();
}

function updateProfile() {
    if ($("profileName")) {
        if (currentUser && authToken) {
            $("profileName").textContent =
                currentUser.name || currentUser.email || "Traveller";

            $("profileSub").textContent =
                currentUser.email || "Welcome back";

            $("avatar").textContent =
                (currentUser.name || currentUser.email || "T")
                    .charAt(0).toUpperCase();

            $("logoutBtn").classList.remove("hidden");
        } else {
            $("profileName").textContent = "Guest traveller";
            $("profileSub").textContent = "Plan your next journey";
            $("avatar").textContent = "G";
            $("logoutBtn").classList.add("hidden");
        }
    }
}

if ($("logoutBtn")) {
    $("logoutBtn").addEventListener("click", () => {
        authToken = null;
        currentUser = null;

        localStorage.removeItem("token");
        localStorage.removeItem("user");

        updateProfile();
        showPage("home");
        toast("Logged out successfully.");
    });
}

document.querySelectorAll("[data-page]").forEach(button => {
    button.addEventListener("click", () => showPage(button.dataset.page));
});

/* PASSWORD VALIDATION */

function validatePassword(password) {
    if (password.length < 8) {
        return "Password must contain at least 8 characters.";
    }

    if (!/[A-Z]/.test(password)) {
        return "Password must contain an uppercase letter.";
    }

    if (!/[a-z]/.test(password)) {
        return "Password must contain a lowercase letter.";
    }

    if (!/[0-9]/.test(password)) {
        return "Password must contain a number.";
    }

    if (!/[^A-Za-z0-9]/.test(password)) {
        return "Password must contain a special character.";
    }

    return "";
}

/* REGISTER */

if ($("registerForm")) {
    $("registerForm").addEventListener("submit", async event => {
        event.preventDefault();
        clearNotice("registerNotice");

        const body = {
            name: $("regName").value.trim(),
            email: $("regEmail").value.trim(),
            phone: $("regPhone").value.trim() || null,
            password: $("regPassword").value
        };

        const passwordError = validatePassword(body.password);

        if (passwordError) {
            showNotice("registerNotice", passwordError);
            return;
        }

        try {
            const data = await api("/register", {
                method: "POST",
                body: JSON.stringify(body)
            });

            if (data.access_token || data.token) {
                setAuth(data);
                toast("Account created successfully.");
                showPage("home");
            } else {
                $("registerForm").reset();
                showPage("login");
                showNotice("loginNotice", "Account created. Please log in.", "success");
            }
        } catch (error) {
            showNotice("registerNotice", error.message);
        }
    });
}

/* LOGIN */

if ($("loginForm")) {
    $("loginForm").addEventListener("submit", async event => {
        event.preventDefault();
        clearNotice("loginNotice");

        const body = {
            email: $("loginEmail").value.trim(),
            password: $("loginPassword").value
        };

        try {
            const data = await api("/login", {
                method: "POST",
                body: JSON.stringify(body)
            });

            setAuth(data);
            toast("Login successful.");
            showPage("home");
        } catch (error) {
            showNotice("loginNotice", error.message);
        }
    });
}

/* FORGOT PASSWORD */

if ($("forgotForm")) {
    $("forgotForm").addEventListener("submit", async event => {
        event.preventDefault();
        clearNotice("forgotNotice");

        const email = $("forgotEmail").value.trim();

        if (!email) {
            showNotice("forgotNotice", "Please enter your registered email.");
            return;
        }

        try {
            await api("/forgot-password", {
                method: "POST",
                body: JSON.stringify({ email })
            });

            showNotice(
                "forgotNotice",
                "If this email is registered, a password reset link will be sent.",
                "success"
            );

            $("forgotForm").reset();
        } catch (error) {
            showNotice("forgotNotice", error.message);
        }
    });
}

/* READ RESET TOKEN FROM EMAIL LINK */

function getResetToken() {
    return new URLSearchParams(window.location.search).get("token");
}

/* RESET PASSWORD */

if ($("resetForm")) {
    $("resetForm").addEventListener("submit", async event => {
        event.preventDefault();
        clearNotice("resetNotice");

        const password = $("newPassword").value;
        const confirmPassword = $("confirmPassword").value;
        const token = getResetToken();

        if (!token) {
            showNotice(
                "resetNotice",
                "Reset link is missing or invalid. Please request a new link."
            );
            return;
        }

        const passwordError = validatePassword(password);

        if (passwordError) {
            showNotice("resetNotice", passwordError);
            return;
        }

        if (password !== confirmPassword) {
            showNotice("resetNotice", "Passwords do not match.");
            return;
        }

        try {
            await api("/reset-password", {
                method: "POST",
                body: JSON.stringify({
                    token: token,
                    new_password: password
                })
            });

            $("resetForm").reset();

            showNotice(
                "resetNotice",
                "Password updated successfully. Please log in.",
                "success"
            );

            window.history.replaceState(
                {},
                document.title,
                window.location.pathname
            );
        } catch (error) {
            showNotice("resetNotice", error.message);
        }
    });
}

/* TRAVEL DATE */

function setDateMinimum() {
    const today = new Date();

    const localDate = [
        today.getFullYear(),
        String(today.getMonth() + 1).padStart(2, "0"),
        String(today.getDate()).padStart(2, "0")
    ].join("-");

    ["homeDate", "travelDate"].forEach(id => {
        if ($(id)) {
            $(id).min = localDate;
            if (!$(id).value) $(id).value = localDate;
        }
    });
}

/* DASHBOARD SEARCH */

if ($("homeSearch")) {
    $("homeSearch").addEventListener("submit", event => {
        event.preventDefault();

        $("source").value = $("homeSource").value.trim();
        $("destination").value = $("homeDestination").value.trim();
        $("travelDate").value = $("homeDate").value;
        $("className").value = $("homeClass").value;
        $("passengers").value = $("homePassengers").value;

        showPage("search");
        $("journeySearch").requestSubmit();
    });
}

/* SEARCH JOURNEY - MATCHES BACKEND SearchIn MODEL */

if ($("journeySearch")) {
    $("journeySearch").addEventListener("submit", async event => {
        event.preventDefault();
        clearNotice("searchNotice");

        const source = $("source").value.trim();
        const destination = $("destination").value.trim();
        const travelDate = $("travelDate").value;

        if (source.toLowerCase() === destination.toLowerCase()) {
            showNotice("searchNotice", "Source and destination cannot be the same.");
            return;
        }

        if (!travelDate) {
            showNotice("searchNotice", "Please select your travel date.");
            return;
        }

        const body = {
            source,
            destination,
            travel_date: travelDate,
            class_name: $("className").value,
            passengers: Number($("passengers").value)
        };

        const button = $("searchBtn");
        if (button) {
            button.disabled = true;
            button.textContent = "Searching...";
        }

        try {
            const data = await api("/search", {
                method: "POST",
                body: JSON.stringify(body)
            });

            searchResults = data;
            renderResults(data);
        } catch (error) {
            showNotice("searchNotice", error.message);
        } finally {
            if (button) {
                button.disabled = false;
                button.textContent = "⌕ Search trains";
            }
        }
    });
}

/* NORMALIZE SEARCH RESULTS FROM BACKEND */

function getOptions(data) {
    if (Array.isArray(data)) return data;

    const options = [];

    (data.direct || []).forEach(option => {
        options.push({
            ...option,
            title: option.title || "Direct journey",
            route_type: "Direct train",
            result_kind: "direct"
        });
    });

    (data.same_train_splits || []).forEach(option => {
        options.push({
            ...option,
            title: option.title || "Same-train split journey",
            route_type: "Same train · Split journey",
            result_kind: "split"
        });
    });

    (data.different_train_splits || []).forEach(option => {
        options.push({
            ...option,
            title: option.title || "Different-train connection",
            route_type: "Different trains · Connection",
            result_kind: "split"
        });
    });

    return options;
}

/* RENDER RESULTS */

function renderResults(data) {
    const container = $("results");
    if (!container) return;

    container.innerHTML = "";

    const options = getOptions(data);

    if (!options.length) {
        container.innerHTML = `
            <div class="empty">
                <div class="empty-icon">🚆</div>
                <b>No journey options found</b>
                Try different stations or another travel date.
            </div>`;
        return;
    }

    const heading = document.createElement("div");
    heading.className = "results-title";

    const title = document.createElement("h2");
    title.textContent = "Available journey options";

    heading.appendChild(title);
    container.appendChild(heading);

    options.forEach((option, index) => {
        const card = document.createElement("div");
        card.className = "option";

        const top = document.createElement("div");
        top.className = "option-top";

        const info = document.createElement("div");

        const name = document.createElement("div");
        name.className = "train-title";
        const legList = option.legs || [];
        name.textContent = legList.length
            ? legList.map(l => `${l.train_number} ${l.train_name}`).join("  +  ")
            : (option.title || `Journey Option ${index + 1}`);

        const sub = document.createElement("div");
        sub.className = "train-sub";
        sub.textContent = option.route_type || "Smart journey option";

        info.append(name, sub);

        top.append(info);
        card.appendChild(top);

        const details = document.createElement("p");
        details.textContent =
            `Duration: ${option.total_duration ?? option.duration ?? "Not specified"}` +
            (legList.length > 1 ? ` · ${legList.length} tickets` : "") +
            (option.layover_min ? ` · ${Math.floor(option.layover_min / 60)}h ${option.layover_min % 60}m layover at ${option.change_at?.name}` : "");

        card.appendChild(details);

        legList.forEach(leg => {
            const row = document.createElement("div");
            row.className = "train-sub";
            const next = leg.arrival_day_offset ? ` (+${leg.arrival_day_offset}d)` : "";
            row.textContent =
                `${leg.from_station.name} ${leg.departure} → ${leg.to_station.name} ${leg.arrival}${next}` +
                ` · ${leg.travel_date} · ${leg.seats_available} seats` +
                (leg.fare ? ` · ${leg.fare.distance_km} km · ${rupee(leg.fare_total)}` : "");
            card.appendChild(row);
        });

        const bookButton = document.createElement("button");
        bookButton.type = "button";
        bookButton.className = "btn btn-primary";
        bookButton.textContent = "Book this journey";

        bookButton.addEventListener("click", () => bookJourney(option));

        const footer = document.createElement("div");
        footer.className = "option-foot";

        const fareBox = document.createElement("div");
        fareBox.className = "fare-box";
        fareBox.innerHTML = `<small>Total fare for ${data.passengers || 1} traveller(s)</small><b>${rupee(option.total_fare)}</b>`;
        footer.append(fareBox, bookButton);

        card.appendChild(footer);
        container.appendChild(card);
    });
}

/* BOOKING FLOW: results -> passenger details -> payment -> confirmation */

function bookJourney(option) {
    if (!authToken) {
        toast("Please log in before booking.");
        showPage("login");
        return;
    }

    if (!(option.legs || []).length) {
        toast("This option does not contain booking leg details.");
        return;
    }

    pending = {
        option,
        className: searchResults.class || $("className")?.value || "Sleeper",
        count: Number(searchResults.passengers || $("passengers")?.value || 1),
        passengers: []
    };

    buildPassengerPage();
    showPage("passengers");
    window.scrollTo(0, 0);
}

function buildPassengerPage() {
    const { option, className, count } = pending;

    const summary = $("journeySummary");
    summary.innerHTML = "";
    const h = document.createElement("h2");
    h.textContent = `Your journey · ${className} · ${count} traveller(s)`;
    summary.appendChild(h);

    option.legs.forEach((leg, i) => {
        const row = document.createElement("div");
        row.className = "summary-leg";
        row.textContent =
            `${option.legs.length > 1 ? `Ticket ${i + 1}: ` : ""}${leg.train_number} ${leg.train_name} · ` +
            `${leg.from_station.name} ${leg.departure} → ${leg.to_station.name} ${leg.arrival}` +
            `${leg.arrival_day_offset ? ` (+${leg.arrival_day_offset}d)` : ""} · ${leg.travel_date} · ${leg.fare.distance_km} km`;
        summary.appendChild(row);
    });

    $("passengerTotal").textContent = rupee(option.total_fare);

    const cards = $("passengerCards");
    cards.innerHTML = "";

    for (let i = 0; i < count; i++) {
        const prev = pending.passengers[i] || {};
        const card = document.createElement("div");
        card.className = "panel passenger-card";
        card.innerHTML = `
            <div class="panel-head"><div><h2>Passenger ${i + 1}</h2></div><span class="pill">TRAVELLER ${i + 1}</span></div>
            <div class="passenger-grid">
                <div class="field"><label>Full name</label><input class="p-name" maxlength="60" placeholder="As on ID proof" required></div>
                <div class="field"><label>Age</label><input class="p-age" type="number" min="1" max="120" placeholder="Age" required></div>
                <div class="field"><label>Gender</label>
                    <select class="p-gender" required>
                        <option value="">Select</option><option>Male</option><option>Female</option><option>Other</option>
                    </select></div>
                <div class="field"><label>Berth preference</label>
                    <select class="p-berth">
                        <option>No preference</option><option>Lower</option><option>Middle</option><option>Upper</option><option>Side Lower</option><option>Side Upper</option>
                    </select></div>
            </div>`;
        card.querySelector(".p-name").value = prev.name || "";
        card.querySelector(".p-age").value = prev.age || "";
        card.querySelector(".p-gender").value = prev.gender || "";
        card.querySelector(".p-berth").value = prev.berth_pref || "No preference";
        cards.appendChild(card);
    }

    // prefill the first passenger with the logged-in user's name (editable)
    const first = cards.querySelector(".p-name");
    if (first && !first.value && currentUser?.name) first.value = currentUser.name;
}

if ($("passengerForm")) {
    $("passengerForm").addEventListener("submit", event => {
        event.preventDefault();
        clearNotice("passengerNotice");

        const list = [];

        for (const card of document.querySelectorAll(".passenger-card")) {
            const name = card.querySelector(".p-name").value.trim();
            const age = Number(card.querySelector(".p-age").value);
            const gender = card.querySelector(".p-gender").value;
            const berth = card.querySelector(".p-berth").value;
            const n = list.length + 1;

            if (!/^[A-Za-z .'-]{1,60}$/.test(name)) {
                showNotice("passengerNotice", `Passenger ${n}: enter a valid name (letters and spaces only).`);
                return;
            }
            if (!Number.isInteger(age) || age < 1 || age > 120) {
                showNotice("passengerNotice", `Passenger ${n}: enter a valid age (1-120).`);
                return;
            }
            if (!gender) {
                showNotice("passengerNotice", `Passenger ${n}: please select gender.`);
                return;
            }
            list.push({ name, age, gender, berth_pref: berth });
        }

        pending.passengers = list;
        buildPaymentPage();
        showPage("payment");
        window.scrollTo(0, 0);
    });
}

function buildPaymentPage() {
    const { option, className, count } = pending;
    $("fareSub").textContent = `${className} · ${count} traveller(s) · ${option.legs.length} ticket(s)`;

    const box = $("fareBreakdown");
    box.innerHTML = "";

    option.legs.forEach((leg, i) => {
        const f = leg.fare;
        const block = document.createElement("div");
        block.className = "fare-block";

        const title = document.createElement("div");
        title.className = "fare-title";
        title.textContent = `${option.legs.length > 1 ? `Ticket ${i + 1}: ` : ""}${leg.from_station.code} → ${leg.to_station.code} · ${f.distance_km} km · ${f.train_type}`;
        block.appendChild(title);

        const lines = [
            [`Base fare (${rupee(f.base_fare)} × ${count})`, f.base_fare * count],
            [`Reservation charge`, f.reservation * count],
            f.superfast ? [`Superfast surcharge`, f.superfast * count] : null,
            f.catering ? [`Catering charges`, f.catering * count] : null,
            f.gst ? [`GST (5%)`, f.gst * count] : null,
            [`Convenience fee (incl. GST)`, f.convenience_fee]
        ].filter(Boolean);

        lines.forEach(([label, amount]) => {
            const row = document.createElement("div");
            row.className = "fare-line";
            const l = document.createElement("span");
            l.textContent = label;
            const r = document.createElement("span");
            r.textContent = rupee(amount);
            row.append(l, r);
            block.appendChild(row);
        });

        const sub = document.createElement("div");
        sub.className = "fare-line fare-sub";
        sub.innerHTML = `<span>Ticket total</span><span>${rupee(leg.fare_total)}</span>`;
        block.appendChild(sub);
        box.appendChild(block);
    });

    const total = document.createElement("div");
    total.className = "fare-line fare-grand";
    total.innerHTML = `<span>Total payable</span><span>${rupee(option.total_fare)}</span>`;
    box.appendChild(total);

    $("payBtn").textContent = `Pay ${rupee(option.total_fare)}`;
}

/* payment method tabs */
let payMethod = "UPI";

document.querySelectorAll(".pay-tab").forEach(tab => {
    tab.addEventListener("click", () => {
        payMethod = tab.dataset.method;
        document.querySelectorAll(".pay-tab").forEach(t => t.classList.toggle("active", t === tab));
        document.querySelectorAll(".pay-pane").forEach(p => p.classList.add("hidden"));
        $("pane-" + payMethod).classList.remove("hidden");
        clearNotice("paymentNotice");
    });
});

if ($("cardNumber")) {
    $("cardNumber").addEventListener("input", e => {
        const digits = e.target.value.replace(/\D/g, "").slice(0, 16);
        e.target.value = digits.replace(/(.{4})/g, "$1 ").trim();
    });
}
if ($("cardExpiry")) {
    $("cardExpiry").addEventListener("input", e => {
        let v = e.target.value.replace(/\D/g, "").slice(0, 4);
        if (v.length > 2) v = v.slice(0, 2) + "/" + v.slice(2);
        e.target.value = v;
    });
}

function collectPayment() {
    if (payMethod === "UPI") {
        const upi = $("upiId").value.trim();
        if (!/^[\w.\-]{2,}@[A-Za-z]{2,}$/.test(upi)) throw new Error("Enter a valid UPI ID (e.g. name@upi).");
        return { method: "UPI", upi_id: upi };
    }
    if (payMethod === "Card") {
        const num = $("cardNumber").value.replace(/\s/g, "");
        if (!/^\d{16}$/.test(num)) throw new Error("Card number must be 16 digits.");
        if (!/^(0[1-9]|1[0-2])\/\d{2}$/.test($("cardExpiry").value)) throw new Error("Card expiry must be MM/YY.");
        if (!/^\d{3}$/.test($("cardCvv").value)) throw new Error("CVV must be 3 digits.");
        return { method: "Card", card_number: num, card_expiry: $("cardExpiry").value, card_cvv: $("cardCvv").value };
    }
    if (!$("bankName").value) throw new Error("Please select a bank.");
    return { method: "NetBanking", bank: $("bankName").value };
}

if ($("paymentForm")) {
    $("paymentForm").addEventListener("submit", async event => {
        event.preventDefault();
        clearNotice("paymentNotice");

        if (!pending) {
            showNotice("paymentNotice", "Your booking session expired. Please search again.");
            return;
        }

        let payment;
        try {
            payment = collectPayment();
        } catch (error) {
            showNotice("paymentNotice", error.message);
            return;
        }

        const body = {
            class_name: pending.className,
            passengers: pending.passengers,
            payment,
            legs: pending.option.legs.map(leg => ({
                train_id: Number(leg.train_id),
                from_station_id: Number(leg.from_station.id),
                to_station_id: Number(leg.to_station.id),
                travel_date: leg.travel_date
            }))
        };

        const button = $("payBtn");
        const label = button.textContent;
        button.disabled = true;
        button.textContent = "Processing payment...";

        try {
            await new Promise(resolve => setTimeout(resolve, 1500));   // fake gateway delay
            const data = await api("/book", { method: "POST", body: JSON.stringify(body) });

            ["cardNumber", "cardCvv", "cardExpiry", "upiId"].forEach(id => { if ($(id)) $(id).value = ""; });
            pending = null;
            renderConfirmation(data);
            showPage("confirmation");
            window.scrollTo(0, 0);
            toast("Payment successful. Booking confirmed.");
        } catch (error) {
            showNotice("paymentNotice", error.message);
        } finally {
            button.disabled = false;
            button.textContent = label;
        }
    });
}

/* BOOKING CONFIRMATION */

function renderConfirmation(data) {
    const container = $("confirmationContent");
    if (!container) return;

    container.innerHTML = "";

    const pay = data.payment || {};
    const payPanel = document.createElement("div");
    payPanel.className = "panel success-panel";
    payPanel.innerHTML = `<h2>✅ Payment successful (demo)</h2>`;
    [
        ["Transaction ID", pay.transaction_id],
        ["Payment method", pay.method],
        ["Amount paid", rupee(pay.amount)]
    ].forEach(([label, value]) => {
        const row = document.createElement("p");
        const strong = document.createElement("strong");
        strong.textContent = label + ": ";
        row.append(strong, document.createTextNode(String(value ?? "N/A")));
        payPanel.appendChild(row);
    });
    container.appendChild(payPanel);

    (data.journey || []).forEach((ticket, i) => {
        const panel = document.createElement("div");
        panel.className = "panel";

        const title = document.createElement("h2");
        title.textContent = `🎫 Ticket ${i + 1} of ${data.journey.length} · Confirmed`;
        panel.appendChild(title);

        [
            ["PNR", ticket.pnr || "N/A"],
            ["Train", `${ticket.train_number || ""} ${ticket.train_name || ""}`],
            ["From", ticket.from || "N/A"],
            ["To", ticket.to || "N/A"],
            ["Travel date", ticket.travel_date || "N/A"],
            ["Class", ticket.class || "N/A"],
            ["Passengers", ticket.seats ?? "N/A"],
            ["Fare", rupee(ticket.fare)],
            ["Status", ticket.status || "Confirmed"]
        ].forEach(([label, value]) => {
            const row = document.createElement("p");
            const strong = document.createElement("strong");
            strong.textContent = label + ": ";
            row.append(strong, document.createTextNode(String(value)));
            panel.appendChild(row);
        });

        container.appendChild(panel);
    });

    const pPanel = document.createElement("div");
    pPanel.className = "panel";
    const ph = document.createElement("h2");
    ph.textContent = "👥 Passengers";
    pPanel.appendChild(ph);

    (data.passengers || []).forEach((p, i) => {
        const row = document.createElement("p");
        row.textContent = `${i + 1}. ${p.name} · ${p.age} yrs · ${p.gender} · ${p.berth_pref}`;
        pPanel.appendChild(row);
    });
    container.appendChild(pPanel);

    const actions = document.createElement("div");
    actions.className = "btn-row";
    actions.innerHTML = `<button class="btn btn-primary" onclick="showPage('bookings')">View my bookings</button>
                         <button class="btn btn-light" onclick="showPage('search')">Book another journey</button>`;
    container.appendChild(actions);
}

/* MY BOOKINGS */

async function loadBookings() {
    const container = $("bookingList");
    if (!container) return;

    container.innerHTML = "";

    if (!authToken) {
        container.innerHTML = `
            <div class="empty">
                <b>Please log in to view bookings</b>
                Your confirmed journeys will appear here.
            </div>`;
        return;
    }

    try {
        const data = await api("/my-bookings");
        const bookings = Array.isArray(data) ? data : data.bookings || [];

        if (!bookings.length) {
            container.innerHTML = `
                <div class="empty">
                    <div class="empty-icon">🎫</div>
                    <b>No bookings found</b>
                    Your journeys will appear here after booking.
                </div>`;
            return;
        }

        bookings.forEach(booking => {
            const row = document.createElement("div");
            row.className = "booking-row";

            const details = document.createElement("div");

            const title = document.createElement("b");
            title.textContent =
                `${booking.from_station || "N/A"} → ${booking.to_station || "N/A"}`;

            const pnr = document.createElement("p");
            pnr.textContent = `PNR: ${booking.pnr_number || "N/A"}`;

            const train = document.createElement("p");
            train.textContent =
                `Train: ${booking.train_number || ""} ${booking.train_name || ""}`;

            const date = document.createElement("p");
            date.textContent = `Date: ${booking.travel_date || "N/A"}`;

            const seats = document.createElement("p");
            seats.textContent = `Passengers: ${booking.num_seats ?? "N/A"}`;

            const fareP = document.createElement("p");
            fareP.textContent = `Class: ${booking.class_name || "N/A"} · Fare: ${booking.total_fare != null ? rupee(booking.total_fare) : "N/A"}`;

            details.append(title, pnr, train, date, seats, fareP);

            if ((booking.passengers || []).length) {
                const names = document.createElement("p");
                names.textContent = "Travellers: " + booking.passengers.map(p => `${p.name} (${p.age})`).join(", ");
                details.appendChild(names);
            }

            const status = document.createElement("span");
            status.className = "status";
            status.textContent = booking.status || "Confirmed";

            row.append(details, status);
            container.appendChild(row);
        });
    } catch (error) {
        showNotice("bookingNotice", error.message);
    }
}

/* LOAD STATIONS */

async function loadStations() {
    try {
        const data = await api("/stations");
        const stations = Array.isArray(data) ? data : data.stations || [];

        const list = $("stationsList");
        if (!list) return;

        list.innerHTML = "";

        stations.forEach(station => {
            const item = document.createElement("option");

            item.value = typeof station === "string"
                ? station
                : station.station_name || station.name || station.station_code || station.code || "";

            list.appendChild(item);
        });
    } catch (error) {
        console.warn("Station list could not be loaded:", error.message);
    }
}

/* TRAIN STATUS (reads timetable.db through /timetable/... endpoints) */

let statusMode = "train";
let scheduleData = null;
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const dash = (v) => (v ? esc(v) : "—");
const bookablePill = (t) => (t.bookable ? ' <span class="pill">BOOKABLE</span>' : "");

function setStatusMode(mode) {
    statusMode = mode;
    document.querySelectorAll(".status-tab").forEach(b => b.classList.toggle("active", b.dataset.mode === mode));
    $("statusLabel").textContent = mode === "train" ? "Train number or name" : "Station code or name";
    $("statusQuery").placeholder = mode === "train" ? "e.g. 12951 or Rajdhani" : "e.g. NDLS or Kota";
    $("statusResults").innerHTML = "";
    clearNotice("statusNotice");
}

function renderTrainList(list) {
    if (!list.length) {
        $("statusResults").innerHTML = '<div class="empty"><div class="empty-icon">🚆</div><b>No train found</b>Try the 5-digit number or part of the name.</div>';
        return;
    }
    $("statusResults").innerHTML = list.map(t => `
        <button type="button" class="train-row" data-train="${esc(t.train_number)}">
            <div><b>${esc(t.train_number)} · ${esc(t.train_name)}${bookablePill(t)}</b>
            <p>${esc(t.from_name)} → ${esc(t.to_name)} · ${esc(t.duration)}</p></div>
            <div class="tr-time">${dash(t.departure)} → ${dash(t.arrival)}</div>
        </button>`).join("");
}

function renderSchedule() {
    const t = scheduleData;
    const showAll = $("showPassing") ? $("showPassing").checked : false;
    const stops = showAll ? t.stops : t.stops.filter(s => s.is_halt);
    const rows = stops.map(s => `
        <tr class="${s.is_halt ? "" : "pass"}">
            <td>${s.seq}</td><td>${esc(s.station_name)}<small>${esc(s.station_code)}</small></td>
            <td>Day ${s.day}</td><td>${dash(s.arrival)}</td><td>${dash(s.departure)}</td>
            <td>${s.halt_min ? s.halt_min + " min" : s.is_halt ? "—" : "passes"}</td>
        </tr>`).join("");
    $("statusResults").innerHTML = `
        <div class="panel">
            <div class="sched-head">
                <div><h2>${esc(t.train_number)} · ${esc(t.train_name)}${bookablePill(t)}</h2>
                <p>${esc(t.from_name)} (${dash(t.departure)}) → ${esc(t.to_name)} (${dash(t.arrival)}) · ${esc(t.duration)} · ${t.distance_km || "—"} km · ${t.halts} halts</p></div>
                <button type="button" class="btn btn-light" id="backToList">← Back</button>
            </div>
            <div class="sched-opts"><label><input type="checkbox" id="showPassing" ${showAll ? "checked" : ""}> Show stations where the train only passes</label></div>
            <div class="sched-wrap"><table class="sched">
                <thead><tr><th>#</th><th>Station</th><th>Day</th><th>Arrives</th><th>Departs</th><th>Halt</th></tr></thead>
                <tbody>${rows}</tbody></table></div>
        </div>`;
    $("showPassing").addEventListener("change", renderSchedule);
    $("backToList").addEventListener("click", () => $("statusForm").requestSubmit());
}

async function openSchedule(number) {
    clearNotice("statusNotice");
    try {
        scheduleData = await api("/timetable/trains/" + encodeURIComponent(number));
        renderSchedule();
    } catch (error) {
        showNotice("statusNotice", error.message);
    }
}

function renderStationBoard(data) {
    const rows = data.trains.map(t => `
        <tr class="${t.is_halt ? "" : "pass"}" data-train="${esc(t.train_number)}" style="cursor:pointer">
            <td>${esc(t.train_number)}${bookablePill(t)}</td><td>${esc(t.train_name)}</td>
            <td>${esc(t.from_name)} → ${esc(t.to_name)}</td><td>${dash(t.arrival)}</td><td>${dash(t.departure)}</td>
            <td>${t.is_halt ? "halts" : "passes"}</td>
        </tr>`).join("");
    $("statusResults").innerHTML = `
        <div class="panel">
            <div class="sched-head"><div><h2>${esc(data.station_name)} (${esc(data.station_code)})</h2>
            <p>${data.total} trains halt here${data.shown < data.total ? " · showing first " + data.shown : ""} · tap a train for its schedule</p></div></div>
            <div class="sched-wrap"><table class="sched">
                <thead><tr><th>Train</th><th>Name</th><th>Route</th><th>Arrives</th><th>Departs</th><th></th></tr></thead>
                <tbody>${rows || '<tr><td colspan="6">No halting trains found.</td></tr>'}</tbody></table></div>
        </div>`;
}

function initStatus() {
    document.querySelectorAll(".status-tab").forEach(b => b.addEventListener("click", () => setStatusMode(b.dataset.mode)));
    $("statusResults").addEventListener("click", event => {
        const target = event.target.closest("[data-train]");
        if (target) openSchedule(target.dataset.train);
    });
    $("statusForm").addEventListener("submit", async event => {
        event.preventDefault();
        clearNotice("statusNotice");
        const q = $("statusQuery").value.trim();
        const button = $("statusBtn");
        button.disabled = true;
        button.textContent = "Searching...";
        try {
            if (statusMode === "train") {
                const list = await api("/timetable/trains?q=" + encodeURIComponent(q));
                if (list.length === 1 || (list.length && list[0].train_number === q)) await openSchedule(list[0].train_number);
                else renderTrainList(list);
            } else {
                renderStationBoard(await api("/timetable/station?q=" + encodeURIComponent(q)));
            }
        } catch (error) {
            $("statusResults").innerHTML = "";
            showNotice("statusNotice", error.message);
        } finally {
            button.disabled = false;
            button.textContent = "Search";
        }
    });
}

/* INITIALIZE */

document.addEventListener("DOMContentLoaded", () => {
    updateProfile();
    setDateMinimum();
    loadStations();
    initStatus();

    // If the reset link contains a token, open the reset page.
    showPage(getResetToken() ? "reset" : "home");
});