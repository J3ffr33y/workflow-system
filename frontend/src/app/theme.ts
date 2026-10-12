import { createTheme, type MantineColorsTuple } from "@mantine/core";

// Eucalyptus: the accent. Deliberately not a SaaS blue.
const eucalyptus: MantineColorsTuple = [
  "#eaf6f3", "#d6ebe5", "#a9d6ca", "#79c0ad", "#53ad95",
  "#3b9f86", "#2f7d6d", "#246a5c", "#185a4d", "#0a4a3e",
]; // prettier-ignore

export const theme = createTheme({
  primaryColor: "eucalyptus",
  primaryShade: 6,
  colors: { eucalyptus },
  fontFamily:
    '"IBM Plex Sans", "PingFang SC", "Microsoft YaHei", "Hiragino Sans GB", system-ui, -apple-system, "Segoe UI", sans-serif',
  headings: {
    fontFamily: '"IBM Plex Sans", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif',
    fontWeight: "600",
  },
  defaultRadius: "sm",
  fontSizes: { xs: "12px", sm: "13.5px", md: "14.5px", lg: "16px", xl: "19px" },
  components: {
    Button: { defaultProps: { radius: "sm" } },
    Modal: { defaultProps: { radius: "md", centered: true } },
    Drawer: { defaultProps: { position: "right" } },
    // Sentence-case labels everywhere; no shouting badges.
    Badge: { styles: { root: { textTransform: "none", fontWeight: 500 } } },
  },
});
