import { Group, Text, Title } from "@mantine/core";
import type { ReactNode } from "react";
import classes from "./Page.module.css";

/** Standard page frame: title row with actions, then content. */
export function Page({
  title,
  subtitle,
  actions,
  children,
  flush = false,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  flush?: boolean;
}) {
  return (
    <div className={classes.page}>
      <header className={classes.header}>
        <div className={classes.titles}>
          <Title order={1} className={classes.title}>
            {title}
          </Title>
          {subtitle && (
            <Text size="sm" c="dimmed">
              {subtitle}
            </Text>
          )}
        </div>
        {actions && <Group gap="xs">{actions}</Group>}
      </header>
      <div className={flush ? classes.flush : classes.body}>{children}</div>
    </div>
  );
}
