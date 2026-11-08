"use client";

import { useMutation } from "@tanstack/react-query";
import { Loader2, SendHorizontal } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { Answer } from "@/contracts";
import { useApi } from "@/lib/api";
import { cn } from "@/lib/utils";

const EXAMPLES = ["How many bedrooms?", "Where are emergency exits?", "Which room has the largest area?", "What is the total wall length?"];

type Turn = { question: string; answer: Answer | null; error?: string };

export function AskPanel({ floorplanId, version, onAnswer }: { floorplanId: string; version: number; onAnswer(ids: string[]): void }) {
  const api = useApi();
  const [text, setText] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const ask = useMutation({
    mutationFn: (question: string) => api.ask(floorplanId, question, version),
    onSuccess: (answer, question) => {
      setTurns((t) => t.map((x) => (x.question === question && !x.answer && !x.error ? { ...x, answer } : x)));
      onAnswer(answer.element_ids);
    },
    onError: (error, question) => setTurns((t) => t.map((x) => (x.question === question && !x.answer ? { ...x, error: error.message } : x))),
  });
  const send = (raw: string) => {
    const question = raw.trim();
    if (!question || ask.isPending) return;
    setTurns((t) => [...t, { question, answer: null }]);
    setText("");
    ask.mutate(question);
  };

  return (
    <div className="flex flex-col gap-3 p-4 text-ui" data-testid="ask">
      <p className="text-muted-foreground">Ask about this plan. Answers come from the building model.</p>
      <div className="flex flex-wrap gap-1">
        {EXAMPLES.map((q) => (
          <Button key={q} size="xs" variant="outline" disabled={ask.isPending} onClick={() => send(q)}>
            {q}
          </Button>
        ))}
      </div>
      <ol className="flex flex-col gap-3" aria-live="polite">
        {turns.map((turn, i) => (
          <li key={i} className="flex flex-col gap-1">
            <p className="font-medium">{turn.question}</p>
            {turn.error && <p className="text-danger">{turn.error}</p>}
            {!turn.answer && !turn.error && <Loader2 className="size-3.5 animate-spin text-muted-foreground" strokeWidth={1.5} aria-label="Working" />}
            {turn.answer && (
              <p className={cn(turn.answer.status === "UNKNOWN" && "text-muted-foreground")} data-testid="answer">
                {turn.answer.answer}
                {turn.answer.source === "llm" && <span className="ml-1 text-micro text-muted-foreground">(AI wording)</span>}
              </p>
            )}
          </li>
        ))}
      </ol>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          send(text);
        }}
      >
        <Input aria-label="Ask about this plan" placeholder="Ask a question" className="h-8 text-ui" maxLength={500} value={text} onChange={(e) => setText(e.target.value)} />
        <Button size="icon-sm" type="submit" aria-label="Send" disabled={ask.isPending || !text.trim()}>
          <SendHorizontal strokeWidth={1.5} />
        </Button>
      </form>
    </div>
  );
}
