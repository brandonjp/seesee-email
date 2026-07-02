// @ts-check
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";

// Read the app version from pyproject.toml at build time so the docs footer
// always reflects the current release without a manual bump here.
const version = readFileSync(
  fileURLToPath(new URL("../pyproject.toml", import.meta.url)),
  "utf8",
).match(/^version = "(.+?)"/m)?.[1];

// https://astro.build/config
export default defineConfig({
  site: "https://seesee.email",
  outDir: "./dist",
  vite: {
    // Expose the version to Astro components (e.g. the custom Footer).
    define: {
      "import.meta.env.SEESEE_VERSION": JSON.stringify(version ?? ""),
    },
  },
  integrations: [
    starlight({
      title: "SeeSee",
      tagline: "See what your apps sent.",
      logo: {
        light: "./src/assets/logo-light.svg",
        dark: "./src/assets/logo-dark.svg",
        replacesTitle: true,
      },
      social: {
        github: "https://github.com/brandonjp/seesee-email",
      },
      customCss: ["./src/styles/custom.css"],
      components: {
        // Custom footer that appends the current SeeSee version.
        Footer: "./src/components/Footer.astro",
      },
      head: [
        {
          tag: "meta",
          attrs: {
            name: "description",
            content:
              "SeeSee is a lightweight, self-hosted email log viewer. See what your apps sent.",
          },
        },

        // --- Analytics (privacy-first, cookieless page-view tracking) ---
        // Standards: shared-ai-docs ANALYTICS_PLAYBOOK.md §7.
        // Only public client IDs are embedded here; no server-side secrets.

        // Umami (self-hosted) — auto-tracks page views, no init needed.
        {
          tag: "script",
          attrs: {
            defer: true,
            src: "https://umami.bpf.fyi/script.js",
            "data-website-id": "a3e20968-f4ea-4576-a8cc-1edfe9c6eef9",
          },
        },

        // OpenPanel (cloud) — official Proxy-based stub queues calls, then the
        // SDK loads from the CDN (always openpanel.dev, even for self-hosted).
        {
          tag: "script",
          content:
            'window.op=window.op||function(){var n=[];return new Proxy(function(){arguments.length&&n.push([].slice.call(arguments))},{get:function(t,r){return"q"===r?n:function(){n.push([r].concat([].slice.call(arguments)))}},has:function(t,r){return"q"===r}})}();' +
            "window.op('init',{clientId:'e2718fe6-14a2-4d03-ba82-ffe48413d145'," +
            "trackScreenViews:true,trackOutgoingLinks:true,trackAttributes:true});",
        },
        {
          tag: "script",
          attrs: {
            src: "https://openpanel.dev/op1.js",
            defer: true,
            async: true,
          },
        },

        // Swetrix (self-hosted API) — SDK from CDN, init after DOM ready.
        // apiURL MUST end in /log for the self-hosted instance.
        {
          tag: "script",
          attrs: { defer: true, src: "https://swetrix.org/swetrix.js" },
        },
        {
          tag: "script",
          content:
            "document.addEventListener('DOMContentLoaded',function(){" +
            "if(typeof swetrix==='undefined')return;" +
            "swetrix.init('C756rzyCXTLr',{apiURL:'https://api.swetrix.bpf.fyi/log'});" +
            "swetrix.trackViews();swetrix.trackErrors();});",
        },
        {
          tag: "noscript",
          content:
            '<img src="https://api.swetrix.bpf.fyi/log/noscript?pid=C756rzyCXTLr" ' +
            'alt="" referrerpolicy="no-referrer-when-downgrade" />',
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
