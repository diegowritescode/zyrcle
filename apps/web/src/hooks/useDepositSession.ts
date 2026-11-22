import { useCallback, useEffect, useRef, useState } from "react";
import { api, liveUrl, type LiveEvent, type PayoutInfo, type Session } from "@/lib/api";
import { ACTIVE, CREDITED } from "@/lib/labels";

const STORE = "zyrcle:session";
const SETTLED = new Set(["confirmed", "failed", "deferred"]);

function remember(id: string | null) {
  try {
    if (id) sessionStorage.setItem(STORE, id);
    else sessionStorage.removeItem(STORE);
  } catch {
    /* storage blocked: a reload loses the session view, not the session */
  }
}

function remembered(): string | null {
  try {
    return sessionStorage.getItem(STORE);
  } catch {
    return null;
  }
}

/**
 * One deposit session, followed live: state changes and scale readings over a WebSocket (with
 * polling if the socket drops), then the advance payment until the Treasury confirms it on chain.
 * Survives a page reload in the same tab.
 */
export function useDepositSession(token: string | null, onPaid?: () => void) {
  const [session, setSession] = useState<Session | null>(null);
  const [weight, setWeight] = useState<number | null>(null);
  const [payout, setPayout] = useState<PayoutInfo | null>(null);
  const [live, setLive] = useState(false);
  const socket = useRef<WebSocket | null>(null);

  const closeSocket = () => {
    socket.current?.close();
    socket.current = null;
    setLive(false);
  };

  const follow = useCallback((s: Session, t: string) => {
    closeSocket();
    setSession(s);
    remember(s.id);
    if (!ACTIVE.has(s.state)) return;
    const ws = new WebSocket(liveUrl(s.id, t));
    ws.onopen = () => setLive(true);
    ws.onmessage = (msg) => {
      const event = JSON.parse(msg.data) as LiveEvent;
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
  }, []);

  const start = useCallback(
    async (t: string, qr: string, material: string) => {
      setWeight(null);
      setPayout(null);
      follow(await api.start(t, qr, material), t);
    },
    [follow],
  );

  const resume = useCallback(
    async (t: string, id: string) => {
      try {
        follow(await api.session(t, id), t);
      } catch {
        remember(null);
      }
    },
    [follow],
  );

  const reset = useCallback(() => {
    closeSocket();
    remember(null);
    setSession(null);
    setWeight(null);
    setPayout(null);
  }, []);

  // Pick up the session this tab was following before a reload.
  useEffect(() => {
    const id = remembered();
    if (token && id && !session) resume(token, id);
  }, [token, session, resume]);

  // Without a live socket, poll the session until it reaches a final state.
  const activeId = session && ACTIVE.has(session.state) ? session.id : null;
  useEffect(() => {
    if (!token || !activeId || live) return;
    const timer = setInterval(async () => {
      const fresh = await api.session(token, activeId).catch(() => null);
      if (fresh) setSession((prev) => (prev?.id === fresh.id ? fresh : prev));
    }, 2000);
    return () => clearInterval(timer);
  }, [token, activeId, live]);

  // Once credited, follow the advance until it is paid on chain (or deferred / failed).
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
