// QR code rendering for the public creator page (Phase 6).
//
// This calls a public, no-API-key QR image service (api.qrserver.com) rather
// than a bundled encoder: correctly generating a QR code (Reed-Solomon error
// correction, mask-pattern selection, etc.) is easy to get subtly wrong, and
// a wrong implementation means a code that fails to scan once printed on a
// business card — a real functional failure, not a cosmetic one. The target
// data here is the creator's own PUBLIC page URL (the whole point of this
// feature is for it to be shared as widely as possible), so nothing sensitive
// leaves the browser.
//
// This is intentionally the only place that constructs the URL — swap to a
// bundled/self-hosted encoder later by changing just this function.
export function qrCodeImageUrl(data: string, sizePx = 320): string {
  const params = new URLSearchParams({
    data,
    size: `${sizePx}x${sizePx}`,
    margin: "2",
    ecc: "M",
  });
  return `https://api.qrserver.com/v1/create-qr-code/?${params.toString()}`;
}
