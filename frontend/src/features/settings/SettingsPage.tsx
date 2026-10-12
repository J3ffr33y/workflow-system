import {
  Anchor,
  Button,
  Group,
  Paper,
  PasswordInput,
  SegmentedControl,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { useCommand, useMe } from "../../shared/api/hooks";
import { Page } from "../../shared/ui/Page";
import { LookupsPanel } from "./LookupsPanel";

export function SettingsPage() {
  const me = useMe();
  const { t, i18n } = useTranslation();
  const [name, setName] = useState(me.data?.user.full_name ?? "");
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const profile = useCommand("identity.update_my_profile", {
    invalidate: [["me"]],
    success: "Profile saved",
  });
  const password = useCommand("identity.change_own_password", { success: "Password changed" });
  const setLocale = (l: string) => {
    localStorage.setItem("locale", l);
    i18n.changeLanguage(l);
    profile.mutate({ locale: l });
  };
  return (
    <Page title="Settings">
      <Stack maw={720} gap="lg">
        <Paper withBorder p="md">
          <Title order={3} size="h5" mb="sm">
            My profile
          </Title>
          <Group align="flex-end">
            <TextInput label="Name" value={name} onChange={(e) => setName(e.currentTarget.value)} w={280} />
            <Button onClick={() => profile.mutate({ full_name: name })} disabled={!name.trim()}>
              Save
            </Button>
          </Group>
          <Text size="sm" fw={500} mt="md" mb={4}>
            Interface language
          </Text>
          <SegmentedControl
            value={i18n.language}
            onChange={setLocale}
            data={[
              { value: "en", label: "English" },
              { value: "zh-CN", label: "中文" },
            ]}
          />
        </Paper>
        <Paper withBorder p="md">
          <Title order={3} size="h5" mb="sm">
            Change password
          </Title>
          <Stack gap="xs" maw={320}>
            <PasswordInput
              label="Current password"
              value={current}
              onChange={(e) => setCurrent(e.currentTarget.value)}
            />
            <PasswordInput
              label="New password"
              description="At least 10 characters, upper and lower case, and a digit."
              value={next}
              onChange={(e) => setNext(e.currentTarget.value)}
            />
            <Button
              w="fit-content"
              disabled={!current || !next}
              loading={password.isPending}
              onClick={() =>
                password.mutate(
                  { current_password: current, new_password: next },
                  { onSuccess: () => (setCurrent(""), setNext("")) },
                )
              }
            >
              Change password
            </Button>
          </Stack>
        </Paper>
        {me.data?.workspaces.some((w) => w.permissions.includes("schema.manage")) && <LookupsPanel />}
        {/* Kept low-key on purpose: useful to the curious, noise for everyone else. */}
        <Anchor component={Link} to="/about/data-model" size="xs" c="dimmed">
          {t("dataModel.link")}
        </Anchor>
      </Stack>
    </Page>
  );
}
