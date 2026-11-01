"use client";

import { useCallback, useSyncExternalStore } from "react";

import { DENSITY_CLASS } from "./density";

// Per-browser UI preferences. `density` also drives the .density-compact class that P6 honours.
const DEFAULTS = {
  density: "comfortable" as "comfortable" | "compact",
  units: "metric" as "px" | "metric",
  sidebar: "expanded" as "expanded" | "collapsed",
};
export type Preferences = typeof DEFAULTS;
export type PreferenceKey = keyof Preferences;

const storageKey = (key: PreferenceKey) => `aec.${key}`;

const listeners = new Set<() => void>();

function read<K extends PreferenceKey>(key: K): Preferences[K] {
  try {
    return (localStorage.getItem(storageKey(key)) as Preferences[K] | null) ?? DEFAULTS[key];
  } catch {
    return DEFAULTS[key]; // storage blocked: the default still renders correctly
  }
}

export function setPreference<K extends PreferenceKey>(key: K, value: Preferences[K]) {
  try {
    localStorage.setItem(storageKey(key), value);
  } catch {
    // storage blocked: the choice lasts for this page view only
  }
  if (key === "density") document.documentElement.classList.toggle(DENSITY_CLASS, value === "compact");
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  window.addEventListener("storage", listener); // other tabs
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

export function usePreference<K extends PreferenceKey>(key: K): [Preferences[K], (value: Preferences[K]) => void] {
  const value = useSyncExternalStore(
    subscribe,
    () => read(key),
    () => DEFAULTS[key],
  );
  return [value, useCallback((v: Preferences[K]) => setPreference(key, v), [key])];
}
