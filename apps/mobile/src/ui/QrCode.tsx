import QRCode from "qrcode";
import { useMemo } from "react";
import Svg, { Rect } from "react-native-svg";
import { colors } from "./theme";

/** A QR code drawn with react-native-svg from the `qrcode` library's module matrix. */
export function QrCode({ value, size = 220 }: { value: string; size?: number }) {
  const modules = useMemo(() => QRCode.create(value, { errorCorrectionLevel: "M" }).modules, [value]);
  const n = modules.size;
  const margin = 2;
  const cell = size / (n + margin * 2);
  const rects = [];
  for (let y = 0; y < n; y++) {
    for (let x = 0; x < n; x++) {
      if (modules.get(y, x)) {
        rects.push(<Rect key={`${x}-${y}`} x={(x + margin) * cell} y={(y + margin) * cell} width={cell} height={cell} fill={colors.forestDark} />);
      }
    }
  }
  return (
    <Svg width={size} height={size} accessibilityLabel="Código QR del cobro">
      <Rect x={0} y={0} width={size} height={size} fill="#ffffff" />
      {rects}
    </Svg>
  );
}
