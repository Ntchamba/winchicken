import React from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import SalairesSection from "../SalairesSection";
import { employeesApi, payrollApi } from "../../../api/endpoints";

// 2026-09-25: payments and the employee list only ever read page 1 (20 rows) — past the 21st
// employee, hours could not be logged. Payments now page with "Afficher plus", the employee
// list is read in full, and marking a payment paid must not fold the opened pages back to 20.

vi.mock("../../../api/endpoints", () => ({
  payrollApi: { salaryPayments: vi.fn(), markPaid: vi.fn(), calculateSalaries: vi.fn(), logHours: vi.fn() },
  employeesApi: { payrollList: vi.fn(), setHourlyRate: vi.fn() },
}));

const payment = (id) => ({
  id, employeeName: `Ouvrier ${id}`, period_month: 8, period_year: 2026, total_hours: "10.00", amount: "5000.00", status: "PENDING",
});
const employee = (id) => ({ id, name: `Employé ${String(id).padStart(2, "0")}`, hourly_rate: 500 });
const page = (rows, next, count) => ({ data: { count, next, results: rows } });

describe("SalairesSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    payrollApi.salaryPayments.mockImplementation(({ page: n }) => Promise.resolve(
      n === 1
        ? page(Array.from({ length: 20 }, (_, i) => payment(i + 1)), "?page=2", 26)
        : page(Array.from({ length: 6 }, (_, i) => payment(i + 21)), null, 26),
    ));
    employeesApi.payrollList.mockImplementation(({ page: n }) => Promise.resolve(
      n === 1
        ? page(Array.from({ length: 20 }, (_, i) => employee(i + 1)), "?page=2", 25)
        : page(Array.from({ length: 5 }, (_, i) => employee(i + 21)), null, 25),
    ));
  });

  test("every employee is offered for hours, not just the first 20", async () => {
    render(<SalairesSection />);
    await waitFor(() => expect(screen.getAllByRole("option", { name: /Employé/ })).toHaveLength(25));
  });

  test("a payment from page 2 marked paid changes in place; the list keeps its 26 rows", async () => {
    payrollApi.markPaid.mockResolvedValue({ data: { ...payment(24), status: "PAID" } });
    const onPaymentRecorded = vi.fn();
    render(<SalairesSection onPaymentRecorded={onPaymentRecorded} />);
    expect(await screen.findByText("20 sur 26 affichés")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Afficher plus" }));
    const row = (await screen.findByText("Ouvrier 24")).closest("tr");

    await userEvent.click(within(row).getByRole("button", { name: "Marquer comme payé" }));
    await waitFor(() => expect(within(row).getByText("Payé")).toBeInTheDocument());
    expect(payrollApi.markPaid).toHaveBeenCalledWith(24);
    expect(screen.getAllByText(/^Ouvrier \d+$/)).toHaveLength(26);
    expect(payrollApi.salaryPayments).toHaveBeenCalledTimes(2);
    expect(onPaymentRecorded).toHaveBeenCalled();
  });
});
