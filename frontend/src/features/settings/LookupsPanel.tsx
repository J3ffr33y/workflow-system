import { Badge, Button, Group, Paper, Select, Stack, Text, TextInput, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../shared/api/client";
import { useCommand } from "../../shared/api/hooks";
import type { LookupList } from "../../shared/api/types";

/** Master data lists (Software, Company...) shared by every workspace. */
export function LookupsPanel() {
  const q = useQuery({ queryKey: ["schema", "lookups"], queryFn: () => api.get<LookupList[]>("/lookups") });
  const [list, setList] = useState<string | null>(null);
  const [label, setLabel] = useState("");
  const add = useCommand("lookups.upsert_value", { invalidate: [["schema"]], success: "Added" });
  const toggle = useCommand("lookups.upsert_value", { invalidate: [["schema"]] });
  const current = q.data?.find((l) => l.key === list) ?? q.data?.[0];
  return (
    <Paper withBorder p="md">
      <Title order={3} size="h5" mb="sm">
        Lists
      </Title>
      <Text size="sm" c="dimmed" mb="sm">
        Values used by list fields on every board. Turning a value off hides it from pickers without touching
        existing items.
      </Text>
      <Select
        w={240}
        data={(q.data ?? []).map((l) => ({ value: l.key, label: l.label }))}
        value={current?.key ?? null}
        onChange={setList}
      />
      {current && (
        <Stack gap={6} mt="sm">
          <Group gap={6}>
            {current.values.map((v) => (
              <Badge
                key={v.id}
                variant={v.is_active ? "light" : "outline"}
                color={v.is_active ? "eucalyptus" : "gray"}
                style={{ textTransform: "none", cursor: "pointer" }}
                onClick={() =>
                  toggle.mutate({
                    list_key: current.key,
                    value_id: v.id,
                    label: v.label,
                    is_active: !v.is_active,
                  })
                }
                title={v.is_active ? "Click to turn off" : "Click to turn on"}
              >
                {v.label}
              </Badge>
            ))}
          </Group>
          <Group>
            <TextInput
              placeholder={`New ${current.label.toLowerCase()} value`}
              value={label}
              onChange={(e) => setLabel(e.currentTarget.value)}
            />
            <Button
              disabled={!label.trim()}
              onClick={() => add.mutate({ list_key: current.key, label }, { onSuccess: () => setLabel("") })}
            >
              Add
            </Button>
          </Group>
        </Stack>
      )}
    </Paper>
  );
}
