import { createContext, useContext } from "react";
import type { OperatorApi } from "./api";

export interface ConsoleSession {
    token: string | null;
    api: OperatorApi;
    signIn: (token: string) => void;
    signOut: () => void;
}

export const ConsoleContext = createContext<ConsoleSession | null>(null);

export function useConsole(): ConsoleSession {
    const value = useContext(ConsoleContext);
    if (!value) throw new Error("useConsole outside ConsoleSessionProvider");
    return value;
}
