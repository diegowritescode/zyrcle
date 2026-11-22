import { accountErrorMessage, type CodeSent } from "@zyrcle/client";
import { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { Button, Muted, Notice } from "@/ui/kit";
import { Field } from "@/ui/Field";
import { colors, space } from "@/ui/theme";

/** Two steps: type an email and get a code there, then type the code. Shared by the recovery
 * email (Cuenta) and the recovery itself (/recover). */
export function EmailCodeForm({
  send,
  submit,
  submitLabel,
  onCancel,
}: {
  send: (email: string) => Promise<CodeSent>;
  /** Resolves when done; throws an ApiError to show its message. */
  submit: (email: string, code: string) => Promise<void>;
  submitLabel: string;
  onCancel?: () => void;
}) {
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [wait, setWait] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (wait <= 0) return;
    const t = setTimeout(() => setWait((w) => w - 1), 1_000);
    return () => clearTimeout(t);
  }, [wait]);

  const run = async (step: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await step();
    } catch (e) {
      setError(accountErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const sendCode = () =>
    run(async () => {
      const sent = await send(email);
      setSentTo(sent.sent_to);
      setWait(sent.resend_in_s);
      setCode("");
    });

  return (
    <View style={{ gap: space(3) }}>
      {error && <Notice text={error} />}
      {sentTo === null ? (
        <>
          <Field
            label="Correo"
            value={email}
            onChangeText={setEmail}
            placeholder="tucorreo@gmail.com"
            keyboardType="email-address"
            autoCapitalize="none"
            autoCorrect={false}
            autoComplete="email"
            textContentType="emailAddress"
            returnKeyType="send"
            onSubmitEditing={sendCode}
          />
          <Button title="Enviarme un código" loading={busy} disabled={!/.+@.+\..+/.test(email.trim())} onPress={sendCode} />
          {onCancel && <Button title="Cancelar" variant="outline" onPress={onCancel} />}
        </>
      ) : (
        <>
          <Muted>
            Te enviamos un código de 6 números a {sentTo}. Si no lo ves en unos minutos, revisa la carpeta de spam.
          </Muted>
          <Field
            label="Código"
            value={code}
            onChangeText={(t) => setCode(t.replace(/\D/g, "").slice(0, 6))}
            placeholder="123456"
            keyboardType="number-pad"
            autoComplete="one-time-code"
            textContentType="oneTimeCode"
            maxLength={6}
            style={styles.code}
          />
          <Button
            title={submitLabel}
            loading={busy}
            disabled={code.length !== 6}
            onPress={() => run(() => submit(email, code))}
          />
          <View style={styles.links}>
            <Text
              accessibilityRole="button"
              accessibilityState={{ disabled: wait > 0 || busy }}
              style={[styles.link, (wait > 0 || busy) && { color: colors.muted }]}
              onPress={wait > 0 || busy ? undefined : sendCode}
            >
              {wait > 0 ? `Reenviar en ${wait} s` : "Reenviar código"}
            </Text>
            <Text
              accessibilityRole="button"
              style={styles.link}
              onPress={() => {
                setSentTo(null);
                setError(null);
              }}
            >
              Cambiar correo
            </Text>
          </View>
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  code: { fontSize: 24, letterSpacing: 8, fontVariant: ["tabular-nums"], textAlign: "center" },
  links: { flexDirection: "row", justifyContent: "space-between" },
  link: { color: colors.forest, fontWeight: "600", fontSize: 14, paddingVertical: space(2) },
});
