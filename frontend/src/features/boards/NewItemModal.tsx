import { Alert, Button, Group, Modal, SimpleGrid, Stack, Text } from "@mantine/core";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, command } from "../../shared/api/client";
import { errorMessage } from "../../shared/api/hooks";
import type { Board } from "../../shared/api/types";
import { FieldInput } from "../../shared/fields/FieldInput";
import type { FieldCtx } from "../../shared/workspace";
import { useQueryClient } from "@tanstack/react-query";
import { NewClientButton } from "../clients/NewClientButton";

export function NewItemModal({
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
  const settings = ctx.schema.workspace.settings ?? {};
  const required: string[] = ["name", "client", ...(settings.required_on_create ?? [])];
  const optionalKeys = ["status", "due_date", "fiscal_year"];
  const cols = ctx.schema.columns.filter(
    (c) =>
      c.editable &&
      c.type !== "period_grid" &&
      (required.includes(c.key) || optionalKeys.includes(c.key) || c.required) &&
      !(c.key === "fiscal_year" && board.period_fiscal_year_id) &&
      !c.hidden_by_default,
  );
  const [values, setValues] = useState<Record<string, any>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const qc = useQueryClient();
  const navigate = useNavigate();

  const set = (k: string, v: any) => setValues((p) => ({ ...p, [k]: v }));
  const missing = required.filter(
    (k) => ctx.columns.has(k) && (values[k] === undefined || values[k] === null || values[k] === ""),
  );

  const submit = async () => {
    setBusy(true);
    setError(null);
    setErrors({});
    try {
      const res = await command("items.create", { board_id: board.id, values });
      qc.invalidateQueries({ queryKey: ["items"] });
      setValues({});
      onClose();
      navigate(`?item=${res.result.id}`);
    } catch (e) {
      if (e instanceof ApiError && e.details?.fields) setErrors(e.details.fields);
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={`New ${ctx.schema.workspace.item_label.toLowerCase()} on ${board.name}`}
      size="lg"
    >
      <Stack>
        {error && (
          <Alert color="red" variant="light">
            {error}
          </Alert>
        )}
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          {cols.map((c) => (
            <div key={c.key}>
              <FieldInput
                col={c}
                ctx={ctx}
                label={`${c.label}${required.includes(c.key) ? " *" : ""}`}
                value={values[c.key] ?? null}
                onChange={(v) => set(c.key, v)}
                clientId={values.client}
                boardId={board.id}
              />
              {c.key === "client" && (
                <Group gap={4} mt={4}>
                  <Text size="xs" c="dimmed">
                    Not in the list?
                  </Text>
                  <NewClientButton compact onCreated={(id) => set("client", id)} />
                </Group>
              )}
              {errors[c.key] && (
                <Text size="xs" c="red" mt={2}>
                  {errors[c.key]}
                </Text>
              )}
            </div>
          ))}
        </SimpleGrid>
        <Text size="xs" c="dimmed">
          Other fields can be filled in on the board or in the item panel after it is created.
        </Text>
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={submit} loading={busy} disabled={missing.length > 0}>
            Create
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
