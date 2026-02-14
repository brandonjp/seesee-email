// @ts-check
import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";

// https://astro.build/config
export default defineConfig({
  site: "https://seesee.email",
  outDir: "./dist",
  integrations: [
    starlight({
      title: "SeeSee",
      tagline: "See what your apps sent.",
      logo: {
        light: "./src/assets/logo-light.svg",
        dark: "./src/assets/logo-dark.svg",
        replacesTitle: false,
      },
      social: {
        github: "https://github.com/brandonjp/seesee-email",
      },
      customCss: ["./src/styles/custom.css"],
      head: [
        {
          tag: "meta",
          attrs: {
            name: "description",
            content:
              "SeeSee is a lightweight, self-hosted email log viewer. See what your apps sent.",
          },
        },
      ],
      sidebar: [
        {
          label: "Getting Started",
          items: [
            { label: "Quick Start", slug: "getting-started/quick-start" },
          ],
        },
        {
          label: "Guides",
          items: [
            { label: "SMTP Ingest", slug: "guides/smtp-ingest" },
            { label: "Docker Deployment", slug: "guides/docker-deployment" },
            { label: "Coolify Deployment", slug: "guides/coolify-deployment" },
            { label: "Integrations", slug: "guides/integrations" },
          ],
        },
        {
          label: "Reference",
          items: [
            { label: "REST API", slug: "reference/api" },
            { label: "Configuration", slug: "reference/configuration" },
          ],
        },
        {
          label: "About",
          items: [
            { label: "Privacy & Compliance", slug: "about/privacy" },
            { label: "Contributing", slug: "about/contributing" },
          ],
        },
      ],
    }),
  ],
});
