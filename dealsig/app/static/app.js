(() => {
  "use strict";

  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const toast = document.querySelector("[data-toast]");
  let toastTimer;

  function notify(message, isError = false) {
    if (!toast) return;
    toast.textContent = message;
    toast.style.background = isError ? "#8f3d35" : "#10201c";
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("show"), 3600);
  }

  document.querySelector("[data-menu-toggle]")?.addEventListener("click", () => {
    document.querySelector("#sidebar")?.classList.toggle("open");
  });

  // Timestamps render server-side as UTC. Rewrite them into the reader's own
  // timezone so a Chicago user is not silently reading GMT clock times.
  (() => {
    const dateFmt = new Intl.DateTimeFormat(undefined, {month: "short", day: "2-digit", year: "numeric"});
    const timeFmt = new Intl.DateTimeFormat(undefined, {hour: "numeric", minute: "2-digit"});
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    document.querySelectorAll("time[datetime]").forEach((el) => {
      const moment = new Date(el.dateTime);
      if (Number.isNaN(moment.valueOf())) return;
      el.textContent = `${dateFmt.format(moment)} · ${timeFmt.format(moment)}`;
      if (zone) el.title = `${moment.toLocaleString()} (${zone})`;
    });

    // The greeting is picked from the UTC hour server-side, which reads as the
    // wrong time of day anywhere west of Greenwich.
    const greeting = document.querySelector("[data-greeting]");
    if (greeting) {
      const hour = new Date().getHours();
      greeting.textContent = `Good ${hour < 12 ? "morning" : hour < 18 ? "afternoon" : "evening"}`;
    }
  })();

  document.querySelectorAll("[data-refresh]").forEach((button) => {
    button.addEventListener("click", async () => {
      const original = button.textContent;
      button.disabled = true;
      button.textContent = "Queuing…";
      try {
        await apiJson("/api/refresh", {source: button.dataset.refresh || "all"});
        notify("Refresh queued. Source health will update when collection completes.");
        button.textContent = "Queued ✓";
        setTimeout(() => { button.textContent = original; button.disabled = false; }, 2400);
      } catch (error) {
        notify(error.message || "Refresh failed", true);
        button.textContent = original;
        button.disabled = false;
      }
    });
  });

  // Contact-form bot check. Ticking the box solves a server-signed proof of
  // work in this tab; the submit button unlocks only once it lands. Uses the
  // platform SHA-256 (no third-party captcha, so the CSP stays 'self').
  const robotCheck = document.querySelector("[data-robot-check]");
  if (robotCheck) {
    const toggle = robotCheck.querySelector("[data-robot-toggle]");
    const counterField = robotCheck.querySelector("[data-pow-counter]");
    const status = robotCheck.querySelector("[data-robot-status]");
    const submit = document.querySelector("[data-contact-submit]");
    const token = robotCheck.querySelector('input[name="challenge_token"]')?.value || "";
    const nonce = token.split(".")[1] || "";
    const bits = Number(robotCheck.dataset.powBits) || 18;
    let solving = false;

    function leadingZeroBits(bytes) {
      let total = 0;
      for (const byte of bytes) {
        if (byte) return total + (8 - byte.toString(2).length);
        total += 8;
      }
      return total;
    }

    async function solve() {
      const encoder = new TextEncoder();
      // Hash in batches: one await per batch instead of per hash keeps the
      // promise overhead from dominating, and yields to the event loop so the
      // page never freezes.
      const BATCH = 1024;
      for (let base = 0; base < 20000000; base += BATCH) {
        const digests = await Promise.all(
          Array.from({length: BATCH}, (_, offset) =>
            crypto.subtle.digest("SHA-256", encoder.encode(`${nonce}:${base + offset}`)))
        );
        for (let offset = 0; offset < BATCH; offset += 1) {
          if (leadingZeroBits(new Uint8Array(digests[offset])) >= bits) return String(base + offset);
        }
      }
      return "";
    }

    function reset(message) {
      counterField.value = "";
      if (submit) submit.disabled = true;
      status.textContent = message;
    }

    toggle?.addEventListener("change", async () => {
      if (!toggle.checked) {
        reset("Tick the box to verify — it runs in your browser, with no third-party tracker.");
        return;
      }
      if (!window.crypto?.subtle || !nonce) {
        toggle.checked = false;
        reset("This browser cannot run the verification step. Reply to any DealSig email instead.");
        return;
      }
      if (solving) return;
      solving = true;
      toggle.disabled = true;
      status.textContent = "Verifying…";
      try {
        const counter = await solve();
        if (!counter) throw new Error("no solution");
        counterField.value = counter;
        status.textContent = "Verified — you can send now.";
        if (submit) submit.disabled = false;
      } catch {
        toggle.checked = false;
        reset("Verification did not finish. Untick and try again.");
      } finally {
        solving = false;
        toggle.disabled = false;
      }
    });
  }

  const calculator = document.querySelector("[data-calculator]");
  if (calculator) {
    calculator.querySelector("[data-analyze]")?.addEventListener("click", async (event) => {
      const button = event.currentTarget;
      const payload = {};
      calculator.querySelectorAll("[data-input]").forEach((input) => {
        payload[input.dataset.input] = Number(input.value || 0);
      });
      button.disabled = true;
      button.textContent = "Calculating…";
      try {
        const body = await apiJson(`/api/listings/${calculator.dataset.listingId}/analyze`, payload);
        const money = new Intl.NumberFormat("en-US", {style: "currency", currency: "USD", maximumFractionDigits: 0});
        calculator.querySelector('[data-output="all_in_cost"]').textContent = money.format(body.all_in_cost);
        calculator.querySelector('[data-output="estimated_profit"]').textContent = money.format(body.estimated_profit);
        calculator.querySelector('[data-output="profit_margin"]').textContent = `${body.profit_margin.toFixed(1)}%`;
        calculator.querySelector('[data-output="score"]').textContent = body.score;
        notify("Scenario recalculated. These assumptions are not saved or guaranteed.");
      } catch (error) {
        notify(error.message || "Analysis failed", true);
      } finally {
        button.disabled = false;
        button.textContent = "Recalculate scenario";
      }
    });
  }

  function fromBase64Url(value) {
    const padded = value.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - value.length % 4) % 4);
    const binary = atob(padded);
    return Uint8Array.from(binary, (char) => char.charCodeAt(0)).buffer;
  }

  function toBase64Url(value) {
    const bytes = new Uint8Array(value);
    let binary = "";
    bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
    return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  function preparePublicKey(options) {
    options.challenge = fromBase64Url(options.challenge);
    if (options.user?.id) options.user.id = fromBase64Url(options.user.id);
    ["excludeCredentials", "allowCredentials"].forEach((key) => {
      if (options[key]) options[key] = options[key].map((item) => ({...item, id: fromBase64Url(item.id)}));
    });
    return options;
  }

  function registrationPayload(credential) {
    return {
      id: credential.id,
      rawId: toBase64Url(credential.rawId),
      type: credential.type,
      authenticatorAttachment: credential.authenticatorAttachment,
      clientExtensionResults: credential.getClientExtensionResults(),
      response: {
        clientDataJSON: toBase64Url(credential.response.clientDataJSON),
        attestationObject: toBase64Url(credential.response.attestationObject),
        transports: credential.response.getTransports ? credential.response.getTransports() : [],
      },
    };
  }

  function authenticationPayload(credential) {
    return {
      id: credential.id,
      rawId: toBase64Url(credential.rawId),
      type: credential.type,
      authenticatorAttachment: credential.authenticatorAttachment,
      clientExtensionResults: credential.getClientExtensionResults(),
      response: {
        clientDataJSON: toBase64Url(credential.response.clientDataJSON),
        authenticatorData: toBase64Url(credential.response.authenticatorData),
        signature: toBase64Url(credential.response.signature),
        userHandle: credential.response.userHandle ? toBase64Url(credential.response.userHandle) : null,
      },
    };
  }

  async function apiJson(url, body = {}) {
    const response = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {"Content-Type": "application/json", "X-CSRF-Token": csrf},
      body: JSON.stringify(body),
    });
    // Parse defensively and only after checking the status: an HTML error body
    // (a paywall page, a proxy 502) would otherwise throw a JSON SyntaxError
    // that masks the real status with "the string did not match the expected
    // pattern".
    let payload = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    if (!response.ok) {
      // 401 and 402 are dead ends for a fetch caller — send them somewhere
      // useful, after a beat so the caller's toast stays readable.
      if (response.status === 401) {
        const next = encodeURIComponent(window.location.pathname);
        setTimeout(() => window.location.assign(`/login?next=${next}`), 1200);
      } else if (response.status === 402) {
        setTimeout(() => window.location.assign(payload?.upgrade_url || "/billing"), 1600);
      }
      throw new Error(payload?.detail || `Request failed (${response.status})`);
    }
    return payload;
  }

  document.querySelector("[data-passkey-register]")?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    if (!window.PublicKeyCredential) return notify("This browser does not support passkeys.", true);
    button.disabled = true;
    button.textContent = "Waiting for your device…";
    try {
      const options = preparePublicKey(await apiJson("/api/passkeys/register/options"));
      const credential = await navigator.credentials.create({publicKey: options});
      await apiJson("/api/passkeys/register/verify", registrationPayload(credential));
      notify("Passkey added. You can now use it from the sign-in page.");
      setTimeout(() => window.location.reload(), 1000);
    } catch (error) {
      notify(error.name === "NotAllowedError" ? "Passkey setup was canceled." : error.message, true);
      button.disabled = false;
      button.textContent = "Add a passkey";
    }
  });

  document.querySelector("[data-passkey-login]")?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    if (!window.PublicKeyCredential) return notify("This browser does not support passkeys.", true);
    button.disabled = true;
    button.textContent = "Waiting for your passkey…";
    try {
      const options = preparePublicKey(await apiJson("/api/passkeys/auth/options"));
      const credential = await navigator.credentials.get({publicKey: options});
      const result = await apiJson("/api/passkeys/auth/verify", authenticationPayload(credential));
      window.location.assign(result.redirect || "/app");
    } catch (error) {
      notify(error.name === "NotAllowedError" ? "Passkey sign-in was canceled." : error.message, true);
      button.disabled = false;
      button.textContent = "⌁ Sign in with a passkey";
    }
  });

  document.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      window.location.assign("/deals");
    }
  });
})();
