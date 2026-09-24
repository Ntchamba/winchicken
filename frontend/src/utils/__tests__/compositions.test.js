import { describe, expect, test } from "vitest";
import { compositionByOutput } from "../compositions";

describe("compositionByOutput", () => {
  test("maps each output to its recipe and base yield", () => {
    expect(compositionByOutput([{ output_item: "MASH", name: "Croissance", base_output_quantity: 100 }]))
      .toEqual({ MASH: { name: "Croissance", baseYield: 100 } });
  });

  test("a recipe without a usable base yield is skipped (null, 0, negative)", () => {
    const map = compositionByOutput([
      { output_item: "A", name: "sans base", base_output_quantity: null },
      { output_item: "B", name: "zéro", base_output_quantity: 0 },
      { output_item: "C", name: "négatif", base_output_quantity: -1 },
    ]);
    expect(map).toEqual({});
  });

  test("the first usable recipe in list order wins — the API lists them by name, like the backend picks", () => {
    const map = compositionByOutput([
      { output_item: "MASH", name: "A-sans-base", base_output_quantity: 0 },
      { output_item: "MASH", name: "B", base_output_quantity: 50 },
      { output_item: "MASH", name: "C", base_output_quantity: 80 },
    ]);
    expect(map.MASH).toEqual({ name: "B", baseYield: 50 });
  });

  test("no compositions, or none passed", () => {
    expect(compositionByOutput([])).toEqual({});
    expect(compositionByOutput()).toEqual({});
  });
});
