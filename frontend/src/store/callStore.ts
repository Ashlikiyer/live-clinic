import { create } from "zustand";

import type { ServerEvent } from "@/realtime/events";

import {
  applyServerEvent,
  initialCallData,
  markInterrupted,
  type BusySlot,
  type CallData,
} from "./reducer";

/** Live audio/UI state that changes often and is never derived from server events. */
interface CallUi {
  startedAt: number | null;
  endedAt: number | null;
  agentSpeaking: boolean;
  micLevel: number;
  muted: boolean;
}

interface CallActions {
  startCall: (now: number) => void;
  applyEvent: (event: ServerEvent) => void;
  interrupt: (turnId: number, playedText: string) => void;
  setBusyDay: (date: string, slots: BusySlot[]) => void;
  selectDate: (date: string) => void;
  markSeen: (panel: "calendar" | "form") => void;
  setAgentSpeaking: (speaking: boolean) => void;
  setMicLevel: (level: number) => void;
  toggleMute: () => void;
  reset: () => void;
}

export type CallStore = CallData & CallUi & CallActions;

const initialUi: CallUi = {
  startedAt: null,
  endedAt: null,
  agentSpeaking: false,
  micLevel: 0,
  muted: false,
};

export const useCallStore = create<CallStore>()((set) => ({
  ...initialCallData,
  ...initialUi,

  startCall: (now) => set({ ...initialCallData, ...initialUi, status: "connecting", startedAt: now }),

  applyEvent: (event) =>
    set((state) => {
      const next = applyServerEvent(state, event);
      if (next.status === "ended" && state.status !== "ended") {
        return { ...next, endedAt: event.ts, agentSpeaking: false, micLevel: 0 };
      }
      return next;
    }),

  interrupt: (turnId, playedText) =>
    set((state) => ({ ...markInterrupted(state, turnId, playedText), agentSpeaking: false })),

  setBusyDay: (date, slots) => set((state) => ({ busy: { ...state.busy, [date]: slots } })),

  selectDate: (date) => set({ calendarDate: date }),

  markSeen: (panel) => set((state) => ({ unseen: { ...state.unseen, [panel]: false } })),

  setAgentSpeaking: (agentSpeaking) => set({ agentSpeaking }),

  setMicLevel: (micLevel) => set({ micLevel }),

  toggleMute: () => set((state) => ({ muted: !state.muted })),

  reset: () => set({ ...initialCallData, ...initialUi }),
}));
