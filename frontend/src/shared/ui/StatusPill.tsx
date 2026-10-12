import { Menu, UnstyledButton } from "@mantine/core";
import type { StatusDef } from "../api/types";
import classes from "./StatusPill.module.css";

/** The one loud element of the UI: a solid block of the status colour. */
export function StatusPill({ status, fill = false }: { status: StatusDef | undefined; fill?: boolean }) {
  if (!status) return <span className={classes.empty}>—</span>;
  return (
    <span
      className={fill ? classes.fill : classes.pill}
      style={{
        background: `var(--mantine-color-${status.color}-${status.color === "gray" ? 3 : 6})`,
        color: status.color === "gray" || status.color === "yellow" ? "var(--ink)" : "white",
      }}
    >
      {status.label}
    </span>
  );
}

export function StatusMenu({
  statuses,
  value,
  onChange,
  disabled,
}: {
  statuses: StatusDef[];
  value: string | null;
  onChange: (key: string) => void;
  disabled?: boolean;
}) {
  const current = statuses.find((s) => s.key === value);
  if (disabled) return <StatusPill status={current} fill />;
  return (
    <Menu position="bottom-start" offset={2} width={260} shadow="md" withinPortal>
      <Menu.Target>
        <UnstyledButton className={classes.target} aria-label={`Status: ${current?.label ?? "none"}`}>
          <StatusPill status={current} fill />
        </UnstyledButton>
      </Menu.Target>
      <Menu.Dropdown className={classes.dropdown}>
        {statuses.map((s) => (
          <Menu.Item key={s.key} onClick={() => s.key !== value && onChange(s.key)} className={classes.item}>
            <StatusPill status={s} fill />
          </Menu.Item>
        ))}
      </Menu.Dropdown>
    </Menu>
  );
}
