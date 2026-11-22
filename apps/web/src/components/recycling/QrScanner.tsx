import { Scanner, setZXingModuleOverrides, type IDetectedBarcode, type IScannerError } from "@yudiel/react-qr-scanner";
import zxingWasm from "zxing-wasm/reader/zxing_reader.wasm?url";

// The QR decoder is a WebAssembly build of ZXing. By default it is fetched from a public CDN; serve
// our own copy instead (same version, and the CSP stays 'self').
setZXingModuleOverrides({
    locateFile: (path: string, prefix: string) => (path.endsWith(".wasm") ? zxingWasm : prefix + path),
});

const MESSAGES: Partial<Record<IScannerError["kind"], string>> = {
    "permission-denied": "No tenemos permiso para usar la cámara. Actívalo o escribe el código a mano.",
    "no-camera": "No encontramos una cámara en este dispositivo. Escribe el código a mano.",
    "in-use": "Otra aplicación está usando la cámara. Ciérrala o escribe el código a mano.",
    "insecure-context": "La cámara solo funciona en una conexión segura (https).",
};

export function QrScanner({ onCode, onError }: { onCode: (raw: string) => void; onError: (message: string) => void }) {
    return (
        <Scanner
            onScan={(codes: IDetectedBarcode[]) => {
                const raw = codes[0]?.rawValue;
                if (raw) onCode(raw);
            }}
            onError={(err: IScannerError) => {
                console.warn(`QR scanner: ${err.kind}: ${err.message}`);
                onError(MESSAGES[err.kind] ?? "No pudimos abrir la cámara. Escribe el código a mano.");
            }}
            // The library's defaults demand at least 640x640, which rejects ordinary 640x480 laptop
            // webcams. Ask for a good resolution without a floor.
            constraints={{ facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 720 } }}
            scanDelay={500}
            classNames={{ container: "w-full rounded-lg overflow-hidden" }}
        />
    );
}
