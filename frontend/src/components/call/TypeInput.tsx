"use client";

import { useState } from "react";

export const MAX_TYPED_CHARS = 300;

/** "Type instead": typed messages take the same path as speech, and Mia still answers aloud. */
export function TypeInput({
  disabled,
  onSend,
  onTyping,
}: {
  disabled: boolean;
  onSend: ((text: string) => void) | null;
  onTyping?: () => void;
}) {
  const [text, setText] = useState("");
  const canSend = !disabled && onSend !== null && text.trim().length > 0;

  return (
    <form
      className="flex gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (!canSend) return;
        onSend(text);
        setText("");
      }}
    >
      <label htmlFor="type-instead" className="sr-only">
        Type instead
      </label>
      <input
        id="type-instead"
        value={text}
        onChange={(e) => {
          setText(e.target.value.slice(0, MAX_TYPED_CHARS));
          onTyping?.();
        }}
        disabled={disabled}
        maxLength={MAX_TYPED_CHARS}
        autoComplete="off"
        placeholder={onSend ? "Type instead..." : "Typing is off in the demo"}
        className="min-w-0 flex-1 rounded-full border border-line bg-surface px-4 py-2 text-sm outline-none focus:border-brand disabled:opacity-50"
      />
      <button
        type="submit"
        disabled={!canSend}
        className="rounded-full bg-brand px-4 py-2 text-sm font-medium text-brand-ink transition hover:opacity-90 disabled:bg-surface-muted disabled:text-ink-muted"
      >
        Send
      </button>
    </form>
  );
}
