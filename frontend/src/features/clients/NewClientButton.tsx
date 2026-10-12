import {
  Alert,
  Anchor,
  Button,
  Group,
  Modal,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { useDebouncedValue, useDisclosure } from "@mantine/hooks";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../shared/api/client";
import { useCommand, useDirectory } from "../../shared/api/hooks";
import { MONTHS } from "../../shared/fields/format";

export const CLIENT_TYPES = [
  { value: "individual", label: "Individual" },
  { value: "company", label: "Company" },
  { value: "partnership", label: "Partnership" },
  { value: "trust", label: "Trust" },
  { value: "smsf", label: "SMSF" },
  { value: "other", label: "Other" },
];
export const ENTITY_TYPES = [
  ...CLIENT_TYPES.slice(0, 5),
  { value: "other_incorporated", label: "Other incorporated entity" },
  { value: "other", label: "Other" },
];

export function NewClientButton({
  onCreated,
  compact = false,
}: {
  onCreated?: (id: string) => void;
  compact?: boolean;
}) {
  const [opened, { open, close }] = useDisclosure();
  const dir = useDirectory();
  const [name, setName] = useState("");
  const [type, setType] = useState("individual");
  const [partner, setPartner] = useState<string | null>(null);
  const [abn, setAbn] = useState("");
  const [yearEnd, setYearEnd] = useState<string | null>("6");
  const [debounced] = useDebouncedValue(name, 300);
  const check = useQuery({
    queryKey: ["client-check", debounced],
    queryFn: () =>
      api.get<{ taken: boolean; existing: any; similar: { id: string; name: string }[] }>(
        "/clients/check-name",
        { name: debounced },
      ),
    enabled: debounced.trim().length > 1,
  });
  const create = useCommand("clients.create", { invalidate: [["clients"]], success: "Client created" });

  const submit = async () => {
    const res = await create.mutateAsync({
      name,
      client_type: type,
      partner_user_id: partner,
      primary_entity: {
        name,
        entity_type: type,
        abn: abn || null,
        year_end_month: yearEnd ? Number(yearEnd) : null,
      },
    });
    close();
    setName("");
    setAbn("");
    onCreated?.(res.result.id);
  };

  return (
    <>
      {compact ? (
        <Anchor component="button" type="button" size="xs" onClick={open}>
          Create a client
        </Anchor>
      ) : (
        <Button onClick={open}>New client</Button>
      )}
      <Modal opened={opened} onClose={close} title="New client" size="lg">
        <Stack>
          <TextInput
            label="Client name"
            required
            value={name}
            onChange={(e) => setName(e.currentTarget.value)}
            data-autofocus
          />
          {check.data?.taken && (
            <Alert color="red" variant="light">
              A client called “{check.data.existing.name}” already exists
              {check.data.existing.is_archived ? " (archived)" : ""}.{" "}
              <Anchor component={Link} to={`/clients/${check.data.existing.id}`} size="sm">
                Open it
              </Anchor>
            </Alert>
          )}
          {!check.data?.taken && !!check.data?.similar.length && (
            <Text size="xs" c="dimmed">
              Similar names: {check.data.similar.map((s) => s.name).join(", ")}
            </Text>
          )}
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <Select
              label="Type"
              data={CLIENT_TYPES}
              value={type}
              onChange={(v) => setType(v ?? "individual")}
            />
            <Select
              label="Responsible partner"
              clearable
              searchable
              data={dir.users.map((u) => ({ value: u.id, label: u.full_name }))}
              value={partner}
              onChange={setPartner}
            />
            <TextInput
              label="ABN"
              value={abn}
              onChange={(e) => setAbn(e.currentTarget.value)}
              placeholder="11 digits"
            />
            <Select
              label="Year end"
              clearable
              data={MONTHS.map((m, i) => ({ value: String(i + 1), label: m }))}
              value={yearEnd}
              onChange={setYearEnd}
            />
          </SimpleGrid>
          <Group justify="flex-end">
            <Button
              onClick={submit}
              disabled={!name.trim() || !!check.data?.taken}
              loading={create.isPending}
            >
              Create client
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}
