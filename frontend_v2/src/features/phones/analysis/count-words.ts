/** "1 record", "2 records". */
export const recordsWords = (n: number) => `${n.toLocaleString("en-US")} ${n === 1 ? "record" : "records"}`
