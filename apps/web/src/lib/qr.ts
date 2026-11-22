/**
 * Container QR codes: `zyrcle://c/<container-id>?code=<access-code>`.
 * The code rotates every 30 s on the container's screen, so a photo of the QR stops working.
 * Mirrors packages/protocol (qr_payload / parse_qr).
 */
export interface ContainerQr {
  containerId: string;
  code: string;
}

const QR = /^zyrcle:\/\/c\/([a-z0-9-]{3,64})\?code=([0-9A-Z]{4,16})$/;

export function parseContainerQr(raw: string): ContainerQr | null {
  const m = QR.exec(raw.trim());
  return m ? { containerId: m[1], code: m[2] } : null;
}

export function containerQr(containerId: string, code: string): string {
  return `zyrcle://c/${containerId}?code=${code}`;
}

/**
 * What the container's screen prints under the QR, for when the camera is not available:
 * `<container-id> <code>`, e.g. `ctr-0001 7KQ2MX`.
 */
export function manualCode(containerId: string, code: string): string {
  return `${containerId} ${code}`;
}

export function parseManualCode(raw: string): ContainerQr | null {
  const m = /^([a-z0-9-]{3,64})\s+([0-9a-z]{4,16})$/i.exec(raw.trim());
  return m ? { containerId: m[1].toLowerCase(), code: m[2].toUpperCase() } : null;
}
