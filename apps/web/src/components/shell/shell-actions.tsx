"use client";

import { createContext, useContext } from "react";

export interface ShellActions {
  createProject: () => void;
  openPalette: () => void;
}

export const ShellActionsContext = createContext<ShellActions>({ createProject: () => {}, openPalette: () => {} });

/** Global actions that any screen can trigger; the shell owns the dialogs. */
export const useShellActions = () => useContext(ShellActionsContext);
