"use client";

import { useEffect } from "react";

import { worker } from "./browser";

let started = false; // StrictMode runs effects twice; start once.

export default function MockWorker() {
  useEffect(() => {
    if (started) return;
    started = true;
    worker.start({ onUnhandledFrame: "bypass", quiet: true }).then(() => globalThis.__AEC_MOCK_RESOLVE__?.());
  }, []);
  return null;
}
