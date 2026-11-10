const labels: Record<string, string> = {
  person: "Person",
  organisation: "Organisation",
  device: "Device",
  vehicle: "Vehicle",
  address: "Address",
  event: "Event",
  other: "Subject",
}

export function dossierTypeLabel(type: string) {
  return Object.hasOwn(labels, type) ? labels[type] : "Subject"
}
