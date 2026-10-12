import {
  Button,
  Checkbox,
  Group,
  Menu,
  Modal,
  SegmentedControl,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { IconCheck, IconChevronDown, IconDeviceFloppy, IconStar, IconTrash } from "@tabler/icons-react";
import { useState } from "react";
import { useCommand } from "../../shared/api/hooks";
import type { SavedView, ViewConfig } from "../../shared/api/types";

export function ViewsMenu({
  views,
  current,
  dirty,
  config,
  workspaceId,
  boardId,
  canShare,
  onSelect,
}: {
  views: SavedView[];
  current: SavedView | null;
  dirty: boolean;
  config: ViewConfig;
  workspaceId: string;
  boardId: string;
  canShare: boolean;
  onSelect: (v: SavedView | null) => void;
}) {
  const [opened, { open, close }] = useDisclosure();
  const [name, setName] = useState("");
  const [scope, setScope] = useState<"personal" | "shared">("personal");
  const [isDefault, setDefault] = useState(false);
  const save = useCommand("views.save", { invalidate: [["views"]], success: "View saved" });
  const del = useCommand("views.delete", { invalidate: [["views"]], success: "View deleted" });

  const canOverwrite = current && (current.is_mine || (current.scope === "shared" && canShare));

  const overwrite = () =>
    current &&
    save.mutate({
      view_id: current.id,
      workspace_id: workspaceId,
      board_id: current.board_id,
      name: current.name,
      scope: current.scope,
      is_default: current.is_default,
      config: config as any,
    });

  const saveNew = async () => {
    const res = await save.mutateAsync({
      workspace_id: workspaceId,
      board_id: boardId,
      name,
      scope,
      is_default: isDefault,
      config: config as any,
    });
    close();
    onSelect({
      id: res.result.id,
      workspace_id: workspaceId,
      board_id: boardId,
      name,
      scope,
      is_default: isDefault,
      is_mine: true,
      config,
    });
  };

  return (
    <>
      <Menu position="bottom-start" shadow="md" width={260}>
        <Menu.Target>
          <Button variant="default" size="xs" rightSection={<IconChevronDown size={14} />}>
            {current?.name ?? "Default view"}
            {dirty && (
              <Text span c="orange.7" ml={4}>
                •
              </Text>
            )}
          </Button>
        </Menu.Target>
        <Menu.Dropdown>
          <Menu.Item onClick={() => onSelect(null)} rightSection={!current ? <IconCheck size={14} /> : null}>
            Default view
          </Menu.Item>
          {views.length > 0 && <Menu.Label>Saved views</Menu.Label>}
          {views.map((v) => (
            <Menu.Item
              key={v.id}
              onClick={() => onSelect(v)}
              leftSection={v.is_default ? <IconStar size={13} /> : null}
              rightSection={current?.id === v.id ? <IconCheck size={14} /> : null}
            >
              {v.name}
              <Text span size="xs" c="dimmed" ml={6}>
                {v.scope === "shared" ? "shared" : "mine"}
              </Text>
            </Menu.Item>
          ))}
          <Menu.Divider />
          {canOverwrite && dirty && (
            <Menu.Item leftSection={<IconDeviceFloppy size={14} />} onClick={overwrite}>
              Save changes to “{current.name}”
            </Menu.Item>
          )}
          <Menu.Item
            leftSection={<IconDeviceFloppy size={14} />}
            onClick={() => {
              setName("");
              open();
            }}
          >
            Save as new view…
          </Menu.Item>
          {current && canOverwrite && (
            <Menu.Item
              color="red"
              leftSection={<IconTrash size={14} />}
              onClick={async () => {
                await del.mutateAsync({ view_id: current.id });
                onSelect(null);
              }}
            >
              Delete “{current.name}”
            </Menu.Item>
          )}
        </Menu.Dropdown>
      </Menu>
      <Modal opened={opened} onClose={close} title="Save view">
        <Stack>
          <TextInput
            label="Name"
            value={name}
            onChange={(e) => setName(e.currentTarget.value)}
            data-autofocus
          />
          {canShare && (
            <div>
              <Text size="sm" fw={500} mb={4}>
                Who can use it
              </Text>
              <SegmentedControl
                value={scope}
                onChange={(v) => setScope(v as any)}
                data={[
                  { value: "personal", label: "Only me" },
                  { value: "shared", label: "Everyone on this board" },
                ]}
              />
            </div>
          )}
          <Checkbox
            label="Open this view by default"
            checked={isDefault}
            onChange={(e) => setDefault(e.currentTarget.checked)}
          />
          <Group justify="flex-end">
            <Button onClick={saveNew} disabled={!name.trim()} loading={save.isPending}>
              Save view
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}
