// What axios rejects with when the request went out and nothing came back (offline, backend
// down, CORS). Tests that simulate "the server is unreachable" must use this shape: since
// campaign 9 (B18) a plain Error is a bug in the page, not a network failure, and is no longer
// worded as "Le serveur est inaccessible".
export const networkError = () => Object.assign(new Error("Network Error"), { isAxiosError: true, code: "ERR_NETWORK", request: {} });
