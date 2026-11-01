export const DENSITY_KEY = "aec.density";
export const DENSITY_CLASS = "density-compact";

/** Inlined in <head> so a compact user never sees the comfortable layout flash. */
export const DENSITY_BOOT_SCRIPT = `try{if(localStorage.getItem("${DENSITY_KEY}")==="compact")document.documentElement.classList.add("${DENSITY_CLASS}")}catch(e){}`;
