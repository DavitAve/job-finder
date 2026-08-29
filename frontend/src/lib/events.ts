export const API_UNAVAILABLE_EVENT = "job-finder:api-unavailable";

export function announceApiUnavailable() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(API_UNAVAILABLE_EVENT));
  }
}
