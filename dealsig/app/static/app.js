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

  document.querySelectorAll("[data-refresh]").forEach((button) => {
    button.addEventListener("click", async () => {
      const original = button.textContent;
      button.disabled = true;
      button.textContent = "Queuing…";
      try {
        const response = await fetch("/api/refresh", {
          method: "POST",
          credentials: "same-origin",
          headers: {"Content-Type": "application/json", "X-CSRF-Token": csrf},
          body: JSON.stringify({source: button.dataset.refresh || "all"}),
        });
        const body = await response.json();
        if (!response.ok) throw new Error(body.detail || "Refresh could not be queued");
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
        const response = await fetch(`/api/listings/${calculator.dataset.listingId}/analyze`, {
          method: "POST",
          credentials: "same-origin",
          headers: {"Content-Type": "application/json", "X-CSRF-Token": csrf},
          body: JSON.stringify(payload),
        });
        const body = await response.json();
        if (!response.ok) throw new Error(body.detail || "Analysis failed");
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
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "The security operation failed");
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
