import type { PhoneReport } from "../types"

export interface PhonePalette {
  hex: string
  name: string
  border: string
  bg: string
  bgSoft: string
  text: string
}

export const PHONE_PALETTE: PhonePalette[] = [
  {
    hex: "#2563eb",
    name: "blue",
    border: "border-blue-500",
    bg: "bg-blue-500",
    bgSoft: "bg-blue-50 dark:bg-blue-950/30",
    text: "text-blue-700 dark:text-blue-300",
  },
  {
    hex: "#dc2626",
    name: "red",
    border: "border-red-500",
    bg: "bg-red-500",
    bgSoft: "bg-red-50 dark:bg-red-950/30",
    text: "text-red-700 dark:text-red-300",
  },
  {
    hex: "#059669",
    name: "emerald",
    border: "border-emerald-500",
    bg: "bg-emerald-500",
    bgSoft: "bg-emerald-50 dark:bg-emerald-950/30",
    text: "text-emerald-700 dark:text-emerald-300",
  },
  {
    hex: "#d97706",
    name: "amber",
    border: "border-amber-500",
    bg: "bg-amber-500",
    bgSoft: "bg-amber-50 dark:bg-amber-950/30",
    text: "text-amber-700 dark:text-amber-300",
  },
  {
    hex: "#7c3aed",
    name: "violet",
    border: "border-violet-500",
    bg: "bg-violet-500",
    bgSoft: "bg-violet-50 dark:bg-violet-950/30",
    text: "text-violet-700 dark:text-violet-300",
  },
  {
    hex: "#0891b2",
    name: "cyan",
    border: "border-cyan-500",
    bg: "bg-cyan-500",
    bgSoft: "bg-cyan-50 dark:bg-cyan-950/30",
    text: "text-cyan-700 dark:text-cyan-300",
  },
  {
    hex: "#db2777",
    name: "pink",
    border: "border-pink-500",
    bg: "bg-pink-500",
    bgSoft: "bg-pink-50 dark:bg-pink-950/30",
    text: "text-pink-700 dark:text-pink-300",
  },
  {
    hex: "#65a30d",
    name: "lime",
    border: "border-lime-500",
    bg: "bg-lime-600",
    bgSoft: "bg-lime-50 dark:bg-lime-950/30",
    text: "text-lime-700 dark:text-lime-300",
  },
]

function hashKey(key: string) {
  let hash = 0
  for (const char of key) {
    hash = (hash * 31 + char.charCodeAt(0)) | 0
  }
  return Math.abs(hash)
}

export function paletteSlotForReport(report: PhoneReport | null | undefined, reports: PhoneReport[] = []) {
  if (typeof report?.display_index === "number" && report.display_index >= 0) {
    return report.display_index % PHONE_PALETTE.length
  }

  if (report?.report_key && reports.length) {
    const index = reports.findIndex((candidate) => candidate.report_key === report.report_key)
    if (index >= 0) return index % PHONE_PALETTE.length
  }

  if (report?.report_key) return hashKey(report.report_key) % PHONE_PALETTE.length
  return 0
}

export function paletteSlotForKey(reportKey: string | null | undefined, reports: PhoneReport[] = []) {
  if (!reportKey) return 0
  const report = reports.find((candidate) => candidate.report_key === reportKey)
  if (report) return paletteSlotForReport(report, reports)
  return hashKey(reportKey) % PHONE_PALETTE.length
}

export function phoneShortLabel(report: PhoneReport | null | undefined, reports: PhoneReport[] = []) {
  if (typeof report?.display_index === "number" && report.display_index >= 0) {
    return `P${report.display_index + 1}`
  }
  if (report?.report_key && reports.length) {
    const index = reports.findIndex((candidate) => candidate.report_key === report.report_key)
    if (index >= 0) return `P${index + 1}`
  }
  return "P?"
}

export function displayDeviceName(report: PhoneReport | null | undefined) {
  if (!report) return "Unknown phone"
  return (
    report.device_name_override ||
    report.device_name ||
    report.device_model ||
    report.phone_number ||
    report.report_key
  )
}

export function getPhoneIdentity(report: PhoneReport | null | undefined, reports: PhoneReport[] = []) {
  const slot = paletteSlotForReport(report, reports)
  const palette = PHONE_PALETTE[slot]
  const short = phoneShortLabel(report, reports)
  const device = displayDeviceName(report)
  const owner = report?.phone_owner_name || report?.owner_name || ""
  return {
    slot,
    palette,
    hex: palette.hex,
    short,
    long: owner ? `${short} - ${device} - ${owner}` : `${short} - ${device}`,
    owner,
    model: report?.device_model || "",
    reportKey: report?.report_key || "",
  }
}

export function getPhoneIdentityByKey(reportKey: string | null | undefined, reports: PhoneReport[] = []) {
  const report = reports.find((candidate) => candidate.report_key === reportKey)
  if (report) return getPhoneIdentity(report, reports)
  const slot = paletteSlotForKey(reportKey, reports)
  const palette = PHONE_PALETTE[slot]
  return {
    slot,
    palette,
    hex: palette.hex,
    short: "P?",
    long: "Unknown phone",
    owner: "",
    model: "",
    reportKey: reportKey || "",
  }
}

export function phoneHexByKey(reportKey: string | null | undefined, reports: PhoneReport[] = []) {
  return getPhoneIdentityByKey(reportKey, reports).hex
}
