// Calls to the two services. The base URLs come from config.js (window.FRASE_CONFIG).
// Every call has a timeout, and every failure becomes an ApiError with a message a person can read.

const TIMEOUT_MS = 10000; // generous: a service that scaled to zero on Azure needs a few seconds to wake up

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status; // HTTP status, or 0 when there was no answer at all
    this.code = code;     // the "error" field of the service's JSON error, e.g. "content_unavailable"
  }
}

async function call(baseUrl, path, { method = "GET", body } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  let response;
  try {
    response = await fetch(baseUrl + path, {
      method,
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (error) {
    const reason = error.name === "AbortError" ? "is taking too long to answer" : "could not be reached";
    throw new ApiError(0, "unreachable", `The service ${reason}. It may be waking up; try again in a few seconds.`);
  } finally {
    clearTimeout(timer);
  }
  const data = await response.json().catch(() => null); // an error page that is not JSON gives null
  if (!response.ok && data?.error) {
    throw new ApiError(response.status, data.error, data.message); // a designed error from our service
  }
  if (!response.ok && [502, 503, 504].includes(response.status)) {
    // Azure itself answers 503 "App port is not ready" while a container that scaled to zero
    // starts and its database resumes (up to about a minute).
    throw new ApiError(response.status, "starting_up",
                       "The service is starting up after being idle. Try again in a few seconds.");
  }
  if (!response.ok) {
    throw new ApiError(response.status, "http_error", `The service answered with status ${response.status}.`);
  }
  return data;
}

export const content = (path, options) => call(window.FRASE_CONFIG.contentUrl, path, options);
export const scheduler = (path, options) => call(window.FRASE_CONFIG.schedulerUrl, path, options);
