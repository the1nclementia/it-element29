import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
  type Dispatch,
  type SetStateAction,
} from 'react';
import { ApiError, request } from '../../lib/api';
import type { InventoryItem, InventoryDocument } from '../inventory/types';
export interface BasketLine {
  item: InventoryItem;
  quantity: number;
}
export interface Draft {
  lines: BasketLine[];
  employee: string;
  date: string;
  comment: string;
  purpose: string;
  external: string;
}
interface Attempt {
  key: string;
  payload: object;
}
interface CommandState {
  attempt?: Attempt;
  pending: boolean;
  error?: Error;
  result?: InventoryDocument;
}
export function today() {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Yekaterinburg',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date());
}
const emptyDraft = (): Draft => ({
  lines: [],
  employee: '',
  date: today(),
  comment: '',
  purpose: 'delivery',
  external: '',
});
interface WarehouseState {
  drafts: Record<string, Draft>;
  setDrafts: Dispatch<SetStateAction<Record<string, Draft>>>;
  commands: Record<string, CommandState>;
  setCommands: Dispatch<SetStateAction<Record<string, CommandState>>>;
}
const State = createContext<WarehouseState | null>(null);
export function WarehouseProvider({ children }: { children: ReactNode }) {
  const [drafts, setDrafts] = useState<Record<string, Draft>>({
    issue: emptyDraft(),
    receipt: emptyDraft(),
  });
  const [commands, setCommands] = useState<Record<string, CommandState>>({});
  const unsettled = Object.values(commands).some(command => !!command.attempt);
  useEffect(() => {
    if (!unsettled) return;
    const protectAttempt = (event: BeforeUnloadEvent) => {event.preventDefault();event.returnValue='';};
    window.addEventListener('beforeunload',protectAttempt);
    return () => window.removeEventListener('beforeunload',protectAttempt);
  }, [unsettled]);
  return (
    <State.Provider value={{ drafts, setDrafts, commands, setCommands }}>
      {children}
    </State.Provider>
  );
}
function useWarehouse() {
  const context = useContext(State);
  if (!context) throw new Error('WarehouseProvider required');
  return context;
}
export function useDraft(kind: 'issue' | 'receipt') {
  const { drafts, setDrafts, commands } = useWarehouse();
  const locked = !!commands[kind]?.attempt;
  const update = (change: Partial<Draft>) => {
    if (!locked)
      setDrafts((previous) => ({
        ...previous,
        [kind]: { ...previous[kind], ...change },
      }));
  };
  const add = (item: InventoryItem) => {
    if (!locked)
      setDrafts((previous) => {
        const draft = previous[kind];
        const existing = draft.lines.find((line) => line.item.id === item.id);
        if (!existing && draft.lines.length >= 100) return previous;
        const lines = existing
          ? draft.lines.map((line) =>
              line.item.id === item.id
                ? { ...line, quantity: Math.min(1000000, line.quantity + 1) }
                : line,
            )
          : [...draft.lines, { item, quantity: 1 }];
        return { ...previous, [kind]: { ...draft, lines } };
      });
  };
  const clear = () =>
    setDrafts((previous) => ({ ...previous, [kind]: emptyDraft() }));
  return { draft: drafts[kind], update, add, clear, locked };
}
export function useCommand(slot: string, path: string) {
  const { commands, setCommands } = useWarehouse();
  const state = commands[slot] ?? { pending: false };
  const update = (next: CommandState) =>
    setCommands((previous) => ({ ...previous, [slot]: next }));
  async function send(payload: object) {
    if (state.pending) return undefined;
    const attempt = state.attempt ?? {
      key: crypto.randomUUID(),
      payload: structuredClone(payload),
    };
    update({ attempt, pending: true });
    try {
      const result = await request<InventoryDocument>(path, {
        method: 'POST',
        body: attempt.payload,
        headers: { 'Idempotency-Key': attempt.key },
      });
      update({ pending: false, result });
      return result;
    } catch (error) {
      const unknown =
        !(error instanceof ApiError) ||
        error.status === 0 ||
        error.status >= 500 ||
        error.code === 'operation_busy';
      update({
        pending: false,
        error: error as Error,
        attempt: unknown ? attempt : undefined,
      });
      return undefined;
    }
  }
  return { ...state, send, locked: !!state.attempt };
}
