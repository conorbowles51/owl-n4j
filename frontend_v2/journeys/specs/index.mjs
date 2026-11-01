import capture from "./cb-capture.mjs"
import interpret from "./cb-interpret.mjs"
import screens from "./cb-screens.mjs"
import pol from "./cb-pol.mjs"
import crossev from "./cb-crossev.mjs"
import approaches from "./cb-approaches.mjs"
import media from "./cb-media.mjs"
import collect from "./lx-collect.mjs"

/** Every journey, by owning job (07 section 11). Written red; each owner turns its own green. */
export const ALL = [...capture, ...interpret, ...screens, ...pol, ...crossev, ...approaches, ...media, ...collect]
