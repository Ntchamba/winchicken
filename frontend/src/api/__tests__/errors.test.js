import { describe, expect, test, vi } from "vitest";
import { getFieldErrors, getServerErrorMessage } from "../errors";

const err = (data) => ({ response: { data } });

describe("getServerErrorMessage", () => {
  test("no response at all means the server was unreachable", () => {
    // What axios rejects with when the request went out and nothing came back.
    expect(getServerErrorMessage({ isAxiosError: true, request: {} })).toMatch(/serveur est inaccessible/);
  });

  test("a bug in the page (no request made) is not reported as an unreachable server", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    const message = getServerErrorMessage(new TypeError("x.toUpperCase is not a function"), "Le protocole n'a pas été enregistré. Réessayez.");
    expect(message).toBe("Le protocole n'a pas été enregistré. Réessayez.");
    expect(message).not.toMatch(/inaccessible/);
    spy.mockRestore();
  });

  test("detail wins, then the first field error, then the fallback", () => {
    expect(getServerErrorMessage(err({ detail: "Refusé.", email: ["x"] }))).toBe("Refusé.");
    expect(getServerErrorMessage(err({ email: ["Email déjà utilisé."] }))).toBe("Email déjà utilisé.");
    expect(getServerErrorMessage(err({}), "Repli")).toBe("Repli");
  });

  // A PUT of a list (the protocol lines) answers per line: {"0": {"non_field_errors": [...]}}.
  // It used to render as "[object Object]".
  test("a per-line error is read through to its message, with the line number", () => {
    const data = { 0: { non_field_errors: ["La fin de la période (jour 15) est avant le début (jour 21)."] } };
    expect(getServerErrorMessage(err(data))).toBe("Ligne 1 : La fin de la période (jour 15) est avant le début (jour 21).");
  });

  test("a nested field error inside a line, and a list of lines with empty entries", () => {
    expect(getServerErrorMessage(err({ lines: [{}, { what: ["Ce champ est obligatoire."] }] })))
      .toBe("Ligne 2 : Ce champ est obligatoire.");
  });

  test("never prints an object", () => {
    expect(getServerErrorMessage(err({ a: { b: { c: ["profond"] } } }))).toBe("profond");
    expect(getServerErrorMessage(err({ a: {} }), "Repli")).toBe("Repli");
  });
});

describe("getFieldErrors", () => {
  test("first message per field, nested ones included, detail excluded", () => {
    expect(getFieldErrors(err({ detail: "d", email: ["e1", "e2"], lines: [{ what: ["w"] }] })))
      .toEqual({ email: "e1", lines: "Ligne 1 : w" });
  });
});

describe("getServerErrorMessage says what to do (phone audit, 2026-09-25)", () => {
  const withStatus = (status, data) => ({ response: { status, data } });

  test("a generic field error names its field; a message of the backend's own is left alone", () => {
    expect(getServerErrorMessage(withStatus(400, { mortality: ["Ce champ est obligatoire."] })))
      .toBe("Mortalité : Ce champ est obligatoire.");
    expect(getServerErrorMessage(withStatus(400, { email: ["Un compte utilise déjà cet email."] })))
      .toBe("Un compte utilise déjà cet email.");
    expect(getServerErrorMessage(withStatus(400, { quantity: ["Un nombre valide est requis."] })))
      .toBe("Quantité : Un nombre valide est requis.");
    expect(getServerErrorMessage(withStatus(400, { name: ["Ce fournisseur existe déjà."] }))).toBe("Ce fournisseur existe déjà.");
    expect(getServerErrorMessage(withStatus(400, { mystery: ["Ce champ est obligatoire."] }))).toBe("Ce champ est obligatoire.");
  });

  test("a server error keeps what failed and adds what to do", () => {
    expect(getServerErrorMessage(withStatus(500, "<html>"), "La vente n'a pas été enregistrée. Réessayez."))
      .toBe("La vente n'a pas été enregistrée. Le serveur a rencontré un problème. Réessayez dans un instant ; si cela continue, prévenez l'administrateur de la ferme.");
  });

  test("a refusal says who to ask", () => {
    expect(getServerErrorMessage(withStatus(403, { detail: "Vous n'avez pas la permission d'effectuer cette action." })))
      .toMatch(/permission.*Demandez à l'administrateur de la ferme/);
  });
});
