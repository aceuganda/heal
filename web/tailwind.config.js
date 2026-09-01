/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: "class",
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",

    // Or if using `src` directory:
    "./src/**/*.{js,ts,jsx,tsx,mdx}",

    // tremor
    "./node_modules/@tremor/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    transparent: "transparent",
    current: "currentColor",
    extend: {
      screens: {
        "2xl": "1420px",
        "3xl": "1700px",
      },
      fontFamily: {
        sans: ["var(--font-inter)"],
      },
      width: {
        "message-xs": "350px",
        "message-sm": "550px",
        "message-default": "740px",
        "searchbar-xs": "380px",
        "searchbar-sm": "660px",
        searchbar: "850px",
        "document-sidebar": "800px",
        "document-sidebar-large": "1000px",
      },
      maxWidth: {
        "document-sidebar": "1000px",
      },
      colors: {
        // ---------------------------------------------------------------
        // Heal palette: quiet clinical teal and calm blue-ink neutrals.
        // Red is deliberately reserved for warnings and destructive states.
        // ---------------------------------------------------------------
        heal: {
          red: {
            50: "#fef3f2",
            100: "#fee4e2",
            200: "#fecdca",
            300: "#fda29b",
            400: "#f97066",
            500: "#f04438",
            600: "#d92d20", // primary action
            700: "#b42318", // pressed / hover
            800: "#912018",
            900: "#7a271a",
          },
          teal: {
            50: "#f0fdfa",
            100: "#ccfbf1",
            200: "#99f6e4",
            300: "#5eead4",
            400: "#2dd4bf",
            500: "#14b8a6",
            600: "#0d9488",
            700: "#0f766e",
            800: "#115e59",
            900: "#134e4a",
          },
          ink: {
            50: "#f8fafb",
            100: "#f1f5f6",
            200: "#e2e8eb",
            300: "#cbd5da",
            400: "#94a3ab",
            500: "#64727c",
            600: "#52606a",
            700: "#3d4a53",
            800: "#29353d",
            900: "#1f2933",
            950: "#11181c",
          },
        },

        // Semantic tokens. Components use these, not the ramps above, so a
        // palette change stays a one-file change.
        link: "#0f766e", // heal.teal.700
        subtle: "#94a3ab", // heal.ink.400
        default: "#64727c", // heal.ink.500
        emphasis: "#3d4a53", // heal.ink.700
        strong: "#1f2933", // heal.ink.900
        inverted: "#ffffff",
        background: "#ffffff",
        "background-emphasis": "#f8fafb",
        "background-strong": "#f1f5f6", // heal.ink.100
        border: "#e2e8eb",
        "border-light": "#f1f5f6",
        "border-strong": "#cbd5da", // heal.ink.300
        "hover-light": "#f0fdfa", // heal.teal.50
        hover: "#f1f5f6", // heal.ink.100
        popup: "#ffffff",
        accent: "#0f766e", // heal.teal.700
        "accent-hover": "#115e59", // heal.teal.800
        highlight: {
          text: "#ccfbf1", // heal.teal.100
        },
        error: "#b42318", // heal.red.700
        success: "#047857", // emerald-700
        user: "#0f766e", // heal.teal.700
        ai: "#1f2933", // heal.ink.900
        // light mode
        tremor: {
          brand: {
            faint: "#f0fdfa", // heal.teal.50
            muted: "#99f6e4", // heal.teal.200
            subtle: "#2dd4bf", // heal.teal.400
            DEFAULT: "#0f766e", // heal.teal.700
            emphasis: "#115e59", // heal.teal.800
            inverted: "#ffffff",
          },
          background: {
            muted: "#f9fafb", // gray-50
            subtle: "#f3f4f6", // gray-100
            DEFAULT: "#ffffff", // white
            emphasis: "#374151", // gray-700
          },
          border: {
            DEFAULT: "#e5e7eb", // gray-200
          },
          ring: {
            DEFAULT: "#e5e7eb", // gray-200
          },
          content: {
            subtle: "#9a9a9e", // heal.ink.400
            DEFAULT: "#6e6e73", // heal.ink.500
            emphasis: "#333336", // heal.ink.700
            strong: "#141416", // heal.ink.900
            inverted: "#ffffff",
          },
        },
        // dark mode
        "dark-tremor": {
          brand: {
            faint: "#102f2c", // heal.teal, deepened for dark surfaces
            muted: "#134e4a", // heal.teal.900
            subtle: "#115e59", // heal.teal.800
            DEFAULT: "#0d9488", // heal.teal.600
            emphasis: "#5eead4", // heal.teal.300
            inverted: "#0a0a0b", // heal.ink.950
          },
          background: {
            muted: "#131A2B", // custom
            subtle: "#1f2937", // gray-800
            DEFAULT: "#111827", // gray-900
            emphasis: "#d1d5db", // gray-300
          },
          border: {
            DEFAULT: "#1f2937", // gray-800
          },
          ring: {
            DEFAULT: "#1f2937", // gray-800
          },
          content: {
            subtle: "#6b7280", // gray-500
            DEFAULT: "#d1d5db", // gray-300
            emphasis: "#f3f4f6", // gray-100
            strong: "#f9fafb", // gray-50
            inverted: "#000000", // black
          },
        },
      },
      boxShadow: {
        // light
        "tremor-input": "0 1px 2px 0 rgb(0 0 0 / 0.05)",
        "tremor-card":
          "0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)",
        "tremor-dropdown":
          "0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)",
        // dark
        "dark-tremor-input": "0 1px 2px 0 rgb(0 0 0 / 0.05)",
        "dark-tremor-card":
          "0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)",
        "dark-tremor-dropdown":
          "0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)",
      },
      borderRadius: {
        "tremor-small": "0.375rem",
        "tremor-default": "0.5rem",
        "tremor-full": "9999px",
      },
      fontSize: {
        "tremor-label": ["0.75rem"],
        "tremor-default": ["0.875rem", { lineHeight: "1.25rem" }],
        "tremor-title": ["1.125rem", { lineHeight: "1.75rem" }],
        "tremor-metric": ["1.875rem", { lineHeight: "2.25rem" }],
      },
    },
  },
  safelist: [
    {
      pattern:
        /^(bg-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-(?:50|100|200|300|400|500|600|700|800|900|950))$/,
      variants: ["hover", "ui-selected"],
    },
    {
      pattern:
        /^(text-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-(?:50|100|200|300|400|500|600|700|800|900|950))$/,
      variants: ["hover", "ui-selected"],
    },
    {
      pattern:
        /^(border-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-(?:50|100|200|300|400|500|600|700|800|900|950))$/,
      variants: ["hover", "ui-selected"],
    },
    {
      pattern:
        /^(ring-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-(?:50|100|200|300|400|500|600|700|800|900|950))$/,
    },
    {
      pattern:
        /^(stroke-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-(?:50|100|200|300|400|500|600|700|800|900|950))$/,
    },
    {
      pattern:
        /^(fill-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-(?:50|100|200|300|400|500|600|700|800|900|950))$/,
    },
  ],
  plugins: [
    require("@tailwindcss/typography"),
    require("@headlessui/tailwindcss"),
  ],
};
