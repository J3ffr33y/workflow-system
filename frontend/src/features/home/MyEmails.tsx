import { Badge, Group, Paper, Text, Title } from "@mantine/core";
import { IconMail } from "@tabler/icons-react";
import { useTranslation } from "react-i18next";

/**
 * Reserved slot for "emails waiting for me". It is a placeholder until the
 * email module exists; keeping the slot here fixes where that work will
 * surface so the page layout doesn't change when it arrives.
 */
export function MyEmails() {
  const { t } = useTranslation();
  return (
    <Paper withBorder p="lg" radius="md" style={{ borderStyle: "dashed" }}>
      <Group justify="space-between" mb="xs">
        <Group gap={8}>
          <IconMail size={18} />
          <Title order={2} size="h4">
            {t("myWork.emails.title")}
          </Title>
        </Group>
        <Badge variant="light" color="gray">
          {t("myWork.emails.soon")}
        </Badge>
      </Group>
      <Text c="dimmed" size="sm">
        {t("myWork.emails.body")}
      </Text>
    </Paper>
  );
}
