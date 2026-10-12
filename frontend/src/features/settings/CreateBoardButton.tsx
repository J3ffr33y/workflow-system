import { Button, Modal, Select, Stack, TextInput, UnstyledButton } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useCommand, useSchema } from "../../shared/api/hooks";

export function CreateBoardButton({ workspaceId, children }: { workspaceId: string; children: ReactNode }) {
  const [opened, { open, close }] = useDisclosure();
  const [name, setName] = useState("");
  const [fy, setFy] = useState<string | null>(null);
  const schema = useSchema(workspaceId);
  const navigate = useNavigate();
  const create = useCommand("boards.create", { invalidate: [["schema"]], success: "Board created" });
  const submit = async () => {
    const res = await create.mutateAsync({ workspace_id: workspaceId, name, period_fiscal_year_id: fy });
    close();
    setName("");
    navigate(`/w/${schema.data?.workspace.key}/b/${res.result.id}`);
  };
  return (
    <>
      <UnstyledButton onClick={open} aria-label="New board" title="New board">
        {children}
      </UnstyledButton>
      <Modal opened={opened} onClose={close} title="New board">
        <Stack>
          <TextInput
            label="Board name"
            value={name}
            onChange={(e) => setName(e.currentTarget.value)}
            data-autofocus
          />
          <Select
            label="Fiscal year (optional)"
            description="Boards tied to a fiscal year let Roll over find the next year's board."
            clearable
            data={(schema.data?.fiscal_years ?? []).map((f) => ({ value: f.id, label: f.label }))}
            value={fy}
            onChange={setFy}
          />
          <Button onClick={submit} disabled={!name.trim()} loading={create.isPending}>
            Create board
          </Button>
        </Stack>
      </Modal>
    </>
  );
}
