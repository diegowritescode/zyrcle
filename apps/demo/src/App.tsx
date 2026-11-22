import { useCallback, useEffect, useRef, useState } from "react";
import QRCode from "qrcode";
import type { PrivateKeyAccount } from "viem/accounts";
import { api, ApiError, liveUrl, signIn, type Container, type Item, type Payout, type Session } from "./api";
import { balancePesos, loadAccount, resetAccount } from "./chain";
import { CHAIN_ID, REPO_URL, RPC_URL } from "./config";
import { FINAL, ITEMS, MATERIALS, STATES, pesos } from "./labels";

function Qr({ value }: { value: string }) {
  const [src, setSrc] = useState("");
  useEffect(() => {
    QRCode.toDataURL(value, { margin: 1, width: 168 }).then(setSrc, () => setSrc(""));
  }, [value]);
  return src ? <img className="qr" src={src} alt={`Código del contenedor: ${value}`} /> : null;
}

function short(hex: string) {
  return `${hex.slice(0, 6)}…${hex.slice(-4)}`;
}

export default function App() {
  const [account, setAccount] = useState<PrivateKeyAccount>(() => loadAccount());
  const [token, setToken] = useState<string | null>(null);
  const [balance, setBalance] = useState<number | null>(null);
  const [containers, setContainers] = useState<Container[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [material, setMaterial] = useState<Record<string, string>>({});
  const [session, setSession] = useState<Session | null>(null);
  const [weight, setWeight] = useState<number | null>(null);
  const [payout, setPayout] = useState<Payout | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const socket = useRef<WebSocket | null>(null);

  const refreshBalance = useCallback(async () => {
    try {
      setBalance(await balancePesos(account.address));
    } catch {
      setBalance(null);
    }
  }, [account]);

  // Sign in with the throwaway wallet, then load the containers and the item catalog.
  useEffect(() => {
    let cancelled = false;
    setToken(null);
    signIn(account)
      .then((t) => !cancelled && setToken(t))
      .catch((e) => !cancelled && setError(`No se pudo iniciar sesión: ${e.message}`));
    refreshBalance();
    api.items().then(setItems).catch(() => setItems([]));
    return () => {
      cancelled = true;
    };
  }, [account, refreshBalance]);

  // Containers refresh every 3 s: their access code rotates every 30 s, like the real screen.
  useEffect(() => {
    const load = () => api.containers().then(setContainers).catch(() => undefined);
    load();
    const id = setInterval(load, 3000);
    return () => clearInterval(id);
  }, []);

  // While a session is final, poll for its advance until the Treasury paid it.
  useEffect(() => {
    if (!session || !token || !["verified", "approved"].includes(session.state)) return;
    const id = setInterval(async () => {
      const me = await api.me(token).catch(() => null);
      const p = me?.payouts.find((x) => x.session_id === session.id) ?? null;
      setPayout(p);
      if (p && ["confirmed", "failed"].includes(p.status)) {
        clearInterval(id);
        refreshBalance();
      }
    }, 2000);
    return () => clearInterval(id);
  }, [session, token, refreshBalance]);

  const follow = (s: Session, t: string) => {
    socket.current?.close();
    const ws = new WebSocket(liveUrl(s.id, t));
    ws.onmessage = (msg) => {
      const event = JSON.parse(msg.data);
      if (event.type === "reading") setWeight(event.weight_g);
      if (event.type === "state") setSession((prev) => ({ ...(prev ?? s), ...event }));
    };
    socket.current = ws;
  };

  const run = async (fn: () => Promise<void>) => {
    setError(null);
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const open = (c: Container) =>
    run(async () => {
      if (!token || !c.qr) return;
      const chosen = material[c.id] ?? c.accepted_materials[0];
      const s = await api.start(token, c.qr, chosen);
      setSession(s);
      setWeight(null);
      setPayout(null);
      follow(s, token);
    });

  const drop = (item: string) =>
    run(async () => {
      if (token && session) await api.drop(token, session.id, item);
    });

  const finish = () =>
    run(async () => {
      if (token && session) await api.finish(token, session.id);
    });

  const lidOpen = session && ["open", "depositing"].includes(session.state);
  const done = session && FINAL.has(session.state);

  return (
    <main>
      <header>
        <h1>Zyrcle</h1>
        <p className="lead">
          Reciclaje trazable: un contenedor pesa lo que depositas, revisa que no sea una piedra y te
          paga en <strong>ZYR</strong>, la moneda de una L1 propia de Avalanche (1 ZYR = 1 peso).
          Los contenedores de esta página son simulados con todos sus sensores; el backend, la
          cadena y los pagos son reales.
        </p>
      </header>

      <section className="card wallet">
        <div>
          <span className="muted">Tu wallet de prueba</span>
          <code title={account.address}>{short(account.address)}</code>
        </div>
        <div>
          <span className="muted">Saldo</span>
          <strong>{balance === null ? "—" : pesos(balance)}</strong>
        </div>
        <button className="ghost" onClick={() => setAccount(resetAccount())} disabled={busy}>
          Nueva wallet
        </button>
        <span className={`status ${token ? "ok" : ""}`}>{token ? "Sesión iniciada con tu firma" : "Firmando…"}</span>
      </section>

      {error && <p className="error">{error}</p>}

      {!session || done ? (
        <section>
          <h2>1. Escanea un contenedor</h2>
          <div className="grid">
            {containers.map((c) => (
              <article key={c.id} className="card container">
                <header>
                  <h3>{c.name}</h3>
                  <span className={`badge ${c.online ? (c.busy ? "warn" : "ok") : "off"}`}>
                    {c.online ? (c.busy ? "Ocupado" : "Disponible") : "Sin conexión"}
                  </span>
                </header>
                {c.qr ? <Qr value={c.qr} /> : <div className="qr placeholder">Esperando código…</div>}
                <label>
                  Material
                  <select
                    value={material[c.id] ?? c.accepted_materials[0]}
                    onChange={(e) => setMaterial({ ...material, [c.id]: e.target.value })}
                  >
                    {c.accepted_materials.map((m) => (
                      <option key={m} value={m}>
                        {MATERIALS[m] ?? m}
                      </option>
                    ))}
                  </select>
                </label>
                <button onClick={() => open(c)} disabled={!token || !c.qr || c.busy || busy}>
                  Escanear y abrir
                </button>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {session && (
        <section className="card session">
          <h2>{done ? "Resultado" : "2. Deposita y cierra"}</h2>
          <p className="state">
            <span className={`dot ${session.state}`} /> {STATES[session.state] ?? session.state} ·{" "}
            {session.container_id} · declarado: {MATERIALS[session.declared_material]}
          </p>
          {!done && (
            <p className="weight">
              Peso en vivo: <strong>{weight === null ? "—" : `${(weight / 1000).toFixed(3)} kg`}</strong>
            </p>
          )}
          {lidOpen && (
            <>
              <div className="items">
                {items.map((i) => (
                  <button key={i.name} className="item" onClick={() => drop(i.name)} disabled={busy}>
                    {ITEMS[i.name] ?? i.name}
                    <small>{i.weight_g} g</small>
                  </button>
                ))}
              </div>
              <button className="primary" onClick={finish} disabled={busy}>
                Terminé
              </button>
              <p className="muted">Si te vas sin tocar "Terminé", el contenedor se cierra solo y te paga igual.</p>
            </>
          )}
          {done && (
            <div className="verdict">
              <p>
                <strong>{session.deposited_g ?? 0} g</strong> · puntaje {session.score ?? "—"}
              </p>
              {session.reasons.length > 0 && (
                <ul>
                  {session.reasons.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              )}
              {["verified", "approved"].includes(session.state) && (
                <p className="payout">
                  Anticipo:{" "}
                  {payout
                    ? `${pesos(payout.amount_cop)} · ${payout.status === "confirmed" ? "pagado en la cadena" : payout.status}`
                    : "en cola…"}
                  {payout?.tx_hash && <code title={payout.tx_hash}> tx {short(payout.tx_hash)}</code>}
                </p>
              )}
              {session.state === "review" && (
                <p className="muted">Un operador revisa este depósito antes de pagarlo.</p>
              )}
              {session.state === "empty" && <p className="muted">No hubo cambio de peso: no hay pago.</p>}
            </div>
          )}
        </section>
      )}

      <footer>
        <p>
          Testnet: ZYR no tiene valor real y el capital semilla de la tesorería es simulado. Chain ID{" "}
          {CHAIN_ID} · <a href={RPC_URL}>RPC</a> · <a href={REPO_URL}>código</a> ·{" "}
          <a href={`${REPO_URL}/blob/main/docs/architecture.md`}>arquitectura</a>
        </p>
      </footer>
    </main>
  );
}
