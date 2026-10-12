import { describe, expect, it } from "vitest";
import type { ColumnSpec, ItemRow } from "../api/types";
import { applyValue, cellValue, fmtDate, fmtYearMonth, grouped } from "./format";

const col = (over: Partial<ColumnSpec>): ColumnSpec => ({
  key: "x",
  label: "X",
  type: "text",
  source: "data",
  kind: "text",
  config: {},
  editable: true,
  required: false,
  group: null,
  position: 0,
  rollover: "carry",
  hidden_by_default: false,
  ...over,
});

const row = {
  id: "1",
  status: "a",
  data: { x: "old" },
  roles: { preparer: ["u1"] },
  mirrors: {},
} as unknown as ItemRow;

describe("format helpers", () => {
  it("formats Australian dates", () => {
    expect(fmtDate("2027-05-15")).toBe("15/05/2027");
    expect(fmtYearMonth("2026-08")).toBe("Aug 2026");
  });

  it("reads and writes values wherever the column lives", () => {
    const data = col({ key: "x" });
    const role = col({ key: "role.preparer", source: "role", config: { role: "preparer" }, type: "users" });
    const core = col({ key: "status", source: "core", type: "status" });
    expect(cellValue(row, data)).toBe("old");
    expect(cellValue(row, role)).toEqual(["u1"]);
    expect(applyValue(row, data, null).data).toEqual({});
    expect(applyValue(row, role, ["u2"]).roles.preparer).toEqual(["u2"]);
    expect(applyValue(row, core, "b").status).toBe("b");
    expect(row.data.x).toBe("old"); // never mutates the original row
  });

  it("groups select options for Mantine", () => {
    expect(
      grouped([
        { value: "a", label: "A", group: "G" },
        { value: "b", label: "B", group: "G" },
      ]),
    ).toEqual([
      {
        group: "G",
        items: [
          { value: "a", label: "A" },
          { value: "b", label: "B" },
        ],
      },
    ]);
  });
});
