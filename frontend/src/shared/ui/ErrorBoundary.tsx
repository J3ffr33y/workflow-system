import { Alert, Button, Stack, Text } from "@mantine/core";
import { Component, type ReactNode } from "react";

/** Keeps one broken screen from blanking the whole app. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <Stack p="xl" maw={640}>
        <Alert color="red" title="This screen failed to load">
          <Text size="sm">{this.state.error.message}</Text>
        </Alert>
        <Button w="fit-content" variant="default" onClick={() => this.setState({ error: null })}>
          Try again
        </Button>
      </Stack>
    );
  }
}
