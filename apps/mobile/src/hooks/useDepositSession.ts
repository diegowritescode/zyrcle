import {
  ACTIVE,
  CREDITED,
  type LiveEvent,
  type PayoutInfo,
  type Session,
} from "@zyrcle/client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, liveUrl } from "@/lib/api";

const SETTLED = new Set(["confirmed", "failed", "deferred"]);

/**
 * One deposit session, followed live: state changes and scale readings over a WebSocket (with
 * polling while the socket is down), then the advance until the Treasury confirms it on chain.
 */
export function useDepositSession(token: string | null, onPaid?: () => void) {
  const [session, setSession] = useState<Session | null>(null);
  const [weight, setWeight] = useState<number | null>(null);
  const [payout, setPayout] = useState<PayoutInfo | null>(null);
  const [live, setLive] = useState(false);
  const socket = useRef<WebSocket | null>(null);

  const closeSocket = useCallback(() => {
    socket.current?.close();
    socket.current = null;
    setLive(false);
  }, []);

  const follow = useCallback(
    (s: Session, t: string) => {
      closeSocket();
      setSession(s);
      if (!ACTIVE.has(s.state)) return;
      const ws = new WebSocket(liveUrl(s.id, t));
      ws.onopen = () => setLive(true);
      ws.onmessage = (msg) => {
        const event = JSON.parse(String(msg.data)) as LiveEvent;
        if (event.type === "reading") {
          setWeight(event.weight_g);
        } else if (event.type === "state") {
          const { type: _type, ...fields } = event;
          setSession((prev) => (prev && prev.id === s.id ? { ...prev, ...fields } : prev));
        }
      };
      ws.onclose = () => {
        if (socket.current === ws) {
          socket.current = null;
          setLive(false);
        }
      };
      socket.current = ws;
    },
    [closeSocket],
  );

  const start = useCallback(
    async (t: string, qr: string, material: string) => {
      setWeight(null);
      setPayout(null);
      follow(await api.start(t, qr, material), t);
    },
    [follow],
  );

  const resume = useCallback(async (t: string, id: string) => follow(await api.session(t, id), t), [follow]);

  const reset = useCallback(() => {
    closeSocket();
    setSession(null);
    setWeight(null);
    setPayout(null);
  }, [closeSocket]);

  const activeId = session && ACTIVE.has(session.state) ? session.id : null;
  useEffect(() => {
    if (!token || !activeId || live) return;
    const timer = setInterval(async () => {
      const fresh = await api.session(token, activeId).catch(() => null);
      if (fresh) setSession((prev) => (prev?.id === fresh.id ? fresh : prev));
    }, 2000);
    return () => clearInterval(timer);
  }, [token, activeId, live]);

  const creditedId = session && CREDITED.has(session.state) ? session.id : null;
  const settled = payout !== null && SETTLED.has(payout.status);
  useEffect(() => {
    if (!token || !creditedId || settled) return;
    const check = async () => {
      const me = await api.me(token).catch(() => null);
      const entry = me?.sessions.find((x) => x.id === creditedId);
      if (entry?.payout) {
        setPayout(entry.payout);
        if (entry.payout.status === "confirmed") onPaid?.();
      }
    };
    check();
    const timer = setInterval(check, 2000);
    return () => clearInterval(timer);
  }, [token, creditedId, settled, onPaid]);

  useEffect(() => () => socket.current?.close(), []);

  return { session, weight, payout, live, start, resume, reset };
}
