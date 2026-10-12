import {
  Button,
  Checkbox,
  Group,
  Modal,
  ScrollArea,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { useState } from "react";
import { useCommand } from "../../shared/api/hooks";
import type { Board } from "../../shared/api/types";
import { StatusPill } from "../../shared/ui/StatusPill";
import type { FieldCtx } from "../../shared/workspace";

export function BoardSettingsModal({
  opened,
  onClose,
  board,
  ctx,
}: {
  opened: boolean;
  onClose: () => void;
  board: Board;
  ctx: FieldCtx;
}) {
  const [name, setName] = useState(board.name);
  const [fy, setFy] = useState<string | null>(board.period_fiscal_year_id);
  const allStatuses = ctx.schema.statuses.filter((s) => !s.is_archived);
  const [statuses, setStatuses] = useState<string[]>(
    board.settings?.statuses ?? allStatuses.map((s) => s.key),
  );
  const allFields = ctx.schema.columns.filter((c) => c.key !== "name");
  const [fields, setFields] = useState<string[]>(board.settings?.fields ?? allFields.map((c) => c.key));
  const update = useCommand("boards.update", { invalidate: [["schema"]], success: "Board saved" });
  const toggle = (list: string[], set: (v: string[]) => void, key: string, on: boolean) =>
    set(on ? [...list, key] : list.filter((k) => k !== key));

  return (
    <Modal opened={opened} onClose={onClose} title="Board settings" size="xl">
      <Stack>
        <Group grow>
          <TextInput label="Name" value={name} onChange={(e) => setName(e.currentTarget.value)} />
          <Select
            label="Fiscal year"
            clearable
            data={ctx.schema.fiscal_years.map((f) => ({ value: f.id, label: f.label }))}
            value={fy}
            onChange={setFy}
          />
        </Group>
        <SimpleGrid cols={2}>
          <div>
            <Text fw={600} size="sm" mb={4}>
              Statuses used on this board
            </Text>
            <ScrollArea h={300}>
              <Stack gap={4}>
                {allStatuses.map((s) => (
                  <Checkbox
                    key={s.key}
                    label={<StatusPill status={s} />}
                    checked={statuses.includes(s.key)}
                    onChange={(e) => toggle(statuses, setStatuses, s.key, e.currentTarget.checked)}
                  />
                ))}
              </Stack>
            </ScrollArea>
          </div>
          <div>
            <Text fw={600} size="sm" mb={4}>
              Fields available on this board
            </Text>
            <ScrollArea h={300}>
              <Stack gap={4}>
                {allFields.map((c) => (
                  <Checkbox
                    key={c.key}
                    label={c.label}
                    checked={fields.includes(c.key)}
                    onChange={(e) => toggle(fields, setFields, c.key, e.currentTarget.checked)}
                  />
                ))}
              </Stack>
            </ScrollArea>
          </div>
        </SimpleGrid>
        <Group justify="flex-end">
          <Button
            loading={update.isPending}
            disabled={!statuses.length}
            onClick={() =>
              update.mutate(
                {
                  board_id: board.id,
                  name,
                  period_fiscal_year_id: fy,
                  clear_period: !fy,
                  settings: {
                    statuses:
                      statuses.length === allStatuses.length
                        ? null
                        : allStatuses.map((s) => s.key).filter((k) => statuses.includes(k)),
                    fields: fields.length === allFields.length ? null : fields,
                  },
                },
                { onSuccess: onClose },
              )
            }
          >
            Save board
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
