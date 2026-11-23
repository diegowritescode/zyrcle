import { useCallback, useMemo, useState, type ReactNode } from "react";
import { operatorApi } from "./api";
import { ConsoleContext } from "./context";

/** The operator's console session (docs/adr/0014). The token lasts a working day; it is kept in
 * this browser's storage so a reload does not sign them out. */
const KEY = "zyrcle-operator-token";

function read(): string | null {
    try {
        return window.localStorage.getItem(KEY);
    } catch {
        return null;
    }
}

function write(token: string | null) {
    try {
        if (token) window.localStorage.setItem(KEY, token);
        else window.localStorage.removeItem(KEY);
    } catch {
        // Private mode or blocked storage: the session simply lasts until the tab closes.
    }
}

export function ConsoleSessionProvider({ children }: { children: ReactNode }) {
    const [token, setToken] = useState<string | null>(read);
    const signIn = useCallback((t: string) => {
        write(t);
        setToken(t);
    }, []);
    const signOut = useCallback(() => {
        write(null);
        setToken(null);
    }, []);
    const api = useMemo(() => operatorApi(token, signOut), [token, signOut]);
    const value = useMemo(() => ({ token, api, signIn, signOut }), [token, api, signIn, signOut]);
    return <ConsoleContext.Provider value={value}>{children}</ConsoleContext.Provider>;
}
