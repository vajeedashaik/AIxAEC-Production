"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export const MAX_RECORDING_MS = 60_000;
const PREFERRED_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"]; // audio/mp4 is what Safari records

export type VoiceStatus = "idle" | "starting" | "recording";

export function pickMimeType(): string | undefined {
  return PREFERRED_TYPES.find((t) => MediaRecorder.isTypeSupported?.(t));
}

function micErrorMessage(e: unknown): string {
  const name = (e as { name?: string } | null)?.name;
  if (name === "NotAllowedError" || name === "SecurityError") return "Microphone access is blocked. Allow it in your browser's site settings, or type instead.";
  if (name === "NotFoundError") return "No microphone found. Plug one in, or type instead.";
  return "The microphone couldn't start. Try again, or type instead.";
}

interface Session {
  recorder?: MediaRecorder;
  stream?: MediaStream;
  timer?: ReturnType<typeof setTimeout>;
  raf?: number;
  audio?: AudioContext;
  cancelled?: boolean;
}

interface Options {
  onRecorded(audio: Blob): void;
  onError(message: string): void;
  /** Called on animation frames with a 0–1 input level; write to the DOM, not state. */
  onLevel?(level: number): void;
}

/** MediaRecorder with a 60 s cap and a live level meter. start/stop are safe to call in any order. */
export function useVoiceRecorder({ onRecorded, onError, onLevel }: Options) {
  const [status, setStatus] = useState<VoiceStatus>("idle");
  const latest = useRef({ onRecorded, onError, onLevel });
  useEffect(() => {
    latest.current = { onRecorded, onError, onLevel };
  });
  const session = useRef<Session | null>(null);

  const release = useCallback(() => {
    const s = session.current;
    session.current = null;
    if (!s) return;
    if (s.timer) clearTimeout(s.timer);
    if (s.raf) cancelAnimationFrame(s.raf);
    s.stream?.getTracks().forEach((t) => t.stop());
    void s.audio?.close?.();
    latest.current.onLevel?.(0);
  }, []);

  const stop = useCallback(() => {
    const s = session.current;
    if (!s) return;
    if (s.recorder?.state === "recording") s.recorder.stop();
    else s.cancelled = true; // released before the mic came up: don't start at all
  }, []);

  const start = useCallback(async () => {
    if (session.current) return;
    if (typeof MediaRecorder === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      latest.current.onError("This browser can't record audio. Type your edit instead.");
      return;
    }
    const s: Session = {};
    session.current = s;
    setStatus("starting");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      s.stream = stream;
      if (s.cancelled || session.current !== s) {
        stream.getTracks().forEach((t) => t.stop());
        if (session.current === s) session.current = null;
        setStatus("idle");
        return;
      }
      const mimeType = pickMimeType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      s.recorder = recorder;
      const chunks: Blob[] = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size) chunks.push(e.data);
      };
      recorder.onstop = () => {
        release();
        setStatus("idle");
        if (chunks.length) latest.current.onRecorded(new Blob(chunks, { type: recorder.mimeType || mimeType || "audio/webm" }));
      };
      recorder.start();
      s.timer = setTimeout(stop, MAX_RECORDING_MS);
      setStatus("recording");

      if (typeof AudioContext !== "undefined") {
        const audio = new AudioContext();
        s.audio = audio;
        const analyser = audio.createAnalyser();
        analyser.fftSize = 256;
        audio.createMediaStreamSource(stream).connect(analyser);
        const data = new Uint8Array(analyser.frequencyBinCount);
        const tick = () => {
          analyser.getByteFrequencyData(data);
          latest.current.onLevel?.(Math.min(1, (data.reduce((a, b) => a + b, 0) / data.length / 255) * 3));
          s.raf = requestAnimationFrame(tick);
        };
        tick();
      }
    } catch (e) {
      release();
      setStatus("idle");
      latest.current.onError(micErrorMessage(e));
    }
  }, [release, stop]);

  useEffect(
    () => () => {
      const s = session.current;
      if (s?.recorder) s.recorder.onstop = null;
      release();
    },
    [release],
  );

  return { status, start, stop };
}
