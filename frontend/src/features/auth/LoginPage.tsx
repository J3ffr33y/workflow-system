import { Alert, Button, PasswordInput, Stack, Text, TextInput, Title } from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api, setCsrf } from "../../shared/api/client";
import { errorMessage } from "../../shared/api/hooks";
import classes from "./LoginPage.module.css";

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const values = { email, password };
    setBusy(true);
    setError(null);
    try {
      const res = await api.post<{ csrf: string }>("/auth/login", values);
      setCsrf(res.csrf);
      await qc.invalidateQueries({ queryKey: ["me"] });
      navigate((location.state as any)?.from ?? "/home", { replace: true });
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={classes.wrap}>
      <form className={classes.card} onSubmit={submit}>
        <Stack gap="md">
          <div>
            <span className={classes.mark} aria-hidden />
            <Title order={2} mt="md">
              Sign in to Workflow
            </Title>
            <Text size="sm" c="dimmed">
              Accounting and Grants boards, clients and automations.
            </Text>
          </div>
          {error && (
            <Alert color="red" variant="light">
              {error}
            </Alert>
          )}
          <TextInput
            label="Email"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.currentTarget.value)}
          />
          <PasswordInput
            label="Password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.currentTarget.value)}
          />
          <Button type="submit" loading={busy} fullWidth>
            Sign in
          </Button>
          <Text size="xs" c="dimmed">
            Forgot your password? Ask an administrator to reset it.
          </Text>
        </Stack>
      </form>
    </div>
  );
}
