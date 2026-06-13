export interface DemoRequest {
  name: string;
  email: string;
  firm: string;
  message: string;
}

/**
 * Single integration point for demo requests.
 *
 * TODO(wire-up): replace the stub below with the real destination when
 * one exists — e.g. a Formspree/Basin endpoint, a backend route, or a
 * CRM webhook. Nothing else in the app needs to change.
 */
export async function submitDemoRequest(request: DemoRequest): Promise<void> {
  // Stub: simulate a successful submission so the UI flow is complete.
  console.info('[arclight] demo request (not wired to a backend yet):', request);
  await new Promise((resolve) => setTimeout(resolve, 700));
}
