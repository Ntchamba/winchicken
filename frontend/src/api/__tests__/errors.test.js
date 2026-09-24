import { describe, expect, test } from "vitest";
import { getFieldErrors, getServerErrorMessage } from "../errors";

const err = (data) => ({ response: { data } });

describe("getServerErrorMessage", () => {
  test("no response at all means the server was unreachable", () => {
    expect(getServerErrorMessage({})).toMatch(/serveur est inaccessible/);
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
