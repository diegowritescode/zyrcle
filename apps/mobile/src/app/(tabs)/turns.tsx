import { useQuery, useQueryClient } from "@tanstack/react-query";
import { bookingErrorMessage, dayLabel, localDay, slotLabel, type Booking, type Slot } from "@zyrcle/client";
import * as Haptics from "expo-haptics";
import { router } from "expo-router";
import { BellRing, CalendarClock, QrCode } from "lucide-react-native";
import { useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { api } from "@/lib/api";
import { REMINDER_MINUTES } from "@/lib/notifications";
import { useNotifications } from "@/notifications/context";
import { confirm } from "@/ui/confirm";
import { Body, Button, Card, Heading, IconBadge, Muted, Notice, Pill, Title } from "@/ui/kit";
import { Screen } from "@/ui/Screen";
import { colors, radius, space } from "@/ui/theme";
import { useWallet } from "@/wallet/context";

const haptic = () => {
  if (Platform.OS !== "web") Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
};

/** Book an hour at a container (docs/adr/0009-time-slots.md) and see the hours already booked. */
export default function Turns() {
  const { token } = useWallet();
  const notifications = useNotifications();
  const queryClient = useQueryClient();
  const [picked, setPicked] = useState<string | null>(null);
  const [day, setDay] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState<string | null>(null);

  const bookings = useQuery({
    queryKey: ["bookings", token],
    queryFn: () => api.bookings(token!),
    enabled: token !== null,
    refetchInterval: 60_000,
  });
  const containers = useQuery({ queryKey: ["containers"], queryFn: api.containers, staleTime: 60_000 });
  const containerId = picked ?? containers.data?.[0]?.id ?? null;
  const slots = useQuery({
    queryKey: ["slots", containerId, day, token],
    queryFn: () => api.slots(token!, containerId!, day ?? undefined),
    enabled: token !== null && containerId !== null,
    refetchInterval: 30_000,
  });
  const today = slots.data?.days[0] ?? localDay();

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["bookings"] });
    queryClient.invalidateQueries({ queryKey: ["slots"] });
  };

  const book = async (slot: Slot) => {
    if (!token || !slots.data) return;
    const where = `${slots.data.container_name} · ${dayLabel(slots.data.day, today)} · ${slotLabel(slot.hour)}`;
    if (!(await confirm("¿Reservar este turno?", where, "Reservar"))) return;
    setError(null);
    setSaving(slot.starts_at);
    try {
      await api.book(token, slots.data.container_id, slot.starts_at);
      haptic();
      refresh();
      if (notifications.permission === "undetermined") {
        const ask = await confirm(
          "¿Te avisamos antes?",
          `Te mandamos una notificación ${REMINDER_MINUTES} minutos antes de tu turno, y cuando te paguen.`,
          "Sí, avísame",
        );
        if (ask) await notifications.enable();
      }
    } catch (e) {
      setError(bookingErrorMessage(e));
      refresh();
    } finally {
      setSaving(null);
    }
  };

  const cancel = async (b: Booking) => {
    if (!token) return;
    const when = `${b.container_name} · ${dayLabel(b.day, today)} · ${slotLabel(b.hour)}`;
    if (!(await confirm("¿Cancelar este turno?", when, "Sí, cancelar", { destructive: true, cancel: "No" }))) return;
    setError(null);
    try {
      await api.cancelBooking(token, b.id);
      refresh();
    } catch (e) {
      setError(bookingErrorMessage(e));
    }
  };

  const mine = bookings.data ?? [];

  return (
    <Screen
      refreshing={bookings.isRefetching || slots.isRefetching}
      onRefresh={() => {
        bookings.refetch();
        slots.refetch();
      }}
    >
      <Title>Turnos</Title>
      <Body>
        Reserva una hora para reciclar sin esperar. Si llegas sin turno, igual entras mientras esa hora tenga cupo.
      </Body>

      {error && <Notice text={error} />}

      <Card style={{ gap: space(3) }}>
        <Heading>Tus turnos</Heading>
        {mine.length === 0 ? (
          <Muted>No tienes turnos reservados.</Muted>
        ) : (
          mine.map((b) => <BookingRow key={b.id} booking={b} today={today} onCancel={() => cancel(b)} />)
        )}
        {mine.length > 0 && notifications.permission === "undetermined" && (
          <Button
            title={`Avisarme ${REMINDER_MINUTES} minutos antes`}
            variant="outline"
            icon={<BellRing color={colors.forest} size={18} />}
            onPress={notifications.enable}
          />
        )}
      </Card>

      <Card style={{ gap: space(4) }}>
        <Heading>Reservar</Heading>

        <View style={{ gap: space(2) }}>
          <Text style={styles.label}>Contenedor</Text>
          {containers.isLoading ? (
            <ActivityIndicator color={colors.emerald} />
          ) : (
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips}>
              {(containers.data ?? []).map((c) => (
                <Chip
                  key={c.id}
                  label={c.name}
                  hint={`${c.site_name} · ${c.host_name}`}
                  selected={c.id === containerId}
                  onPress={() => {
                    setPicked(c.id);
                    setError(null);
                  }}
                />
              ))}
            </ScrollView>
          )}
        </View>

        {slots.data && (
          <View style={{ gap: space(2) }}>
            <Text style={styles.label}>Día</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips}>
              {slots.data.days.map((d) => (
                <Chip key={d} label={dayLabel(d, today)} selected={d === slots.data.day} onPress={() => setDay(d)} />
              ))}
            </ScrollView>
          </View>
        )}

        {slots.isLoading ? (
          <ActivityIndicator color={colors.emerald} />
        ) : slots.data && slots.data.slots.length === 0 ? (
          <Muted>Este contenedor no abre ese día.</Muted>
        ) : (
          slots.data && (
            <View style={{ gap: space(2) }}>
              <Text style={styles.label}>Hora · {slots.data.capacity} cupos por hora</Text>
              <View style={styles.grid} accessibilityRole="list">
                {slots.data.slots
                  .filter((s) => s.state !== "past")
                  .map((s) => (
                    <SlotCell key={s.starts_at} slot={s} saving={saving === s.starts_at} onPress={() => book(s)} />
                  ))}
              </View>
            </View>
          )
        )}
        {slots.error && <Notice text={bookingErrorMessage(slots.error)} />}
      </Card>
    </Screen>
  );
}

function BookingRow({ booking: b, today, onCancel }: { booking: Booking; today: string; onCancel: () => void }) {
  const now = b.state === "now";
  return (
    <View style={styles.booking}>
      <IconBadge size={40}>
        <CalendarClock color={colors.white} size={20} />
      </IconBadge>
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={styles.bookingTitle}>
          {dayLabel(b.day, today)} · {slotLabel(b.hour)}
        </Text>
        <Muted>{b.container_name}</Muted>
        <View style={styles.bookingActions}>
          {b.state === "used" ? (
            <Pill label="Ya reciclaste" tone="ok" />
          ) : now ? (
            <Pill label="Es ahora" tone="ok" />
          ) : (
            <Pill label="Reservado" tone="info" />
          )}
          {b.state !== "used" && (
            <Text accessibilityRole="button" style={styles.cancel} onPress={onCancel}>
              Cancelar
            </Text>
          )}
        </View>
        {now && (
          <Button
            title="Escanear el contenedor"
            icon={<QrCode color={colors.white} size={18} />}
            onPress={() => router.push("/scan")}
            style={{ marginTop: space(2), minHeight: 44 }}
          />
        )}
      </View>
    </View>
  );
}

function Chip({ label, hint, selected, onPress }: { label: string; hint?: string; selected: boolean; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[styles.chip, selected && styles.chipSelected]}
    >
      <Text style={[styles.chipText, selected && { color: colors.white }]}>{label}</Text>
      {hint && <Text style={[styles.chipHint, selected && { color: "rgba(255,255,255,0.85)" }]}>{hint}</Text>}
    </Pressable>
  );
}

function SlotCell({ slot, saving, onPress }: { slot: Slot; saving: boolean; onPress: () => void }) {
  const left = slot.capacity - slot.taken;
  const note = slot.mine ? "Tu turno" : left <= 0 ? "Lleno" : `${left} ${left === 1 ? "cupo" : "cupos"}`;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${slotLabel(slot.hour)}, ${note}`}
      accessibilityState={{ disabled: !slot.available }}
      disabled={!slot.available || saving}
      onPress={onPress}
      style={({ pressed }) => [
        styles.cell,
        slot.mine && styles.cellMine,
        !slot.available && !slot.mine && styles.cellOff,
        pressed && { opacity: 0.8 },
      ]}
    >
      {saving ? (
        <ActivityIndicator color={colors.emerald} />
      ) : (
        <>
          <Text style={[styles.cellHour, !slot.available && !slot.mine && { color: colors.muted }]}>
            {slotLabel(slot.hour).split(" – ")[0]}
          </Text>
          <Text style={[styles.cellNote, slot.mine && { color: colors.emeraldDark, fontWeight: "600" }]}>
            {slot.state === "now" && !slot.mine ? `Ahora · ${note}` : note}
          </Text>
        </>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  label: { fontSize: 13, fontWeight: "600", color: colors.textSoft, textTransform: "uppercase", letterSpacing: 0.4 },
  chips: { gap: space(2), paddingRight: space(2) },
  chip: {
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.white,
    borderRadius: radius.md,
    paddingHorizontal: space(3),
    paddingVertical: space(2),
    minHeight: 44,
    justifyContent: "center",
  },
  chipSelected: { backgroundColor: colors.emerald, borderColor: colors.emerald },
  chipText: { fontSize: 14, fontWeight: "600", color: colors.forestDark },
  chipHint: { fontSize: 11, color: colors.muted, marginTop: 1 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: space(2) },
  cell: {
    width: "31.5%",
    minHeight: 60,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.white,
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: space(2),
  },
  cellMine: { borderColor: colors.emerald, backgroundColor: colors.emeraldTint },
  cellOff: { backgroundColor: colors.tint },
  cellHour: { fontSize: 15, fontWeight: "700", color: colors.forestDark, fontVariant: ["tabular-nums"] },
  cellNote: { fontSize: 12, color: colors.muted, marginTop: 2 },
  booking: { flexDirection: "row", gap: space(3), alignItems: "flex-start", paddingVertical: space(2) },
  bookingTitle: { fontSize: 15, fontWeight: "600", color: colors.forestDark },
  bookingActions: { flexDirection: "row", alignItems: "center", gap: space(3), marginTop: space(1) },
  cancel: { color: colors.danger, fontWeight: "600", fontSize: 14, paddingVertical: space(1) },
});
