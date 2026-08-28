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
        // Heal palette: a white page, carried by red and black.
        //
        // `red` is the brand and every action. It is a deep clinical red
        // rather than an alarm red, so it can hold large surfaces without
        // shouting at a health worker reading it all day.
        //
        // `ink` is the neutral ramp -- warm blacks for text and chrome.
        // Blue and indigo are gone from the design entirely.
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
          ink: {
            50: "#f8f8f8",
            100: "#f1f1f1",
            200: "#e4e4e5",
            300: "#c9c9cb",
            400: "#9a9a9e",
            500: "#6e6e73",
            600: "#4b4b4f",
            700: "#333336",
            800: "#1f1f22",
            900: "#141416",
            950: "#0a0a0b",
          },
        },

        // Semantic tokens. Components use these, not the ramps above, so a
        // palette change stays a one-file change.
        link: "#d92d20", // heal.red.600
        subtle: "#9a9a9e", // heal.ink.400
        default: "#6e6e73", // heal.ink.500
        emphasis: "#333336", // heal.ink.700
        strong: "#141416", // heal.ink.900
        inverted: "#ffffff",
        background: "#ffffff", // the page is white, not gray-50
        "background-emphasis": "#fafafa",
        "background-strong": "#f1f1f1", // heal.ink.100
        border: "#e8e8e9",
        "border-light": "#f3f3f4",
        "border-strong": "#c9c9cb", // heal.ink.300
        "hover-light": "#fef3f2", // heal.red.50 -- hover reads as red
        hover: "#f1f1f1", // heal.ink.100
        popup: "#ffffff",
        accent: "#d92d20", // heal.red.600
        "accent-hover": "#b42318", // heal.red.700
        highlight: {
          text: "#fee4e2", // heal.red.100 -- search highlight, was yellow
        },
        // Error shares the brand hue, so it is pitched darker than `accent`
        // and should always be paired with an icon or a wash, never colour
        // alone. See the note in the UI section of the plan.
        error: "#912018", // heal.red.800
        success: "#047857", // emerald-700
        user: "#d92d20", // heal.red.600
        ai: "#141416", // heal.ink.900
        // light mode
        tremor: {
          brand: {
            faint: "#fef3f2", // heal.red.50
            muted: "#fecdca", // heal.red.200
            subtle: "#f97066", // heal.red.400
            DEFAULT: "#d92d20", // heal.red.600
            emphasis: "#b42318", // heal.red.700
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
            faint: "#2a0f0d", // heal.red, deepened for dark surfaces
            muted: "#7a271a", // heal.red.900
            subtle: "#912018", // heal.red.800
            DEFAULT: "#d92d20", // heal.red.600
            emphasis: "#f97066", // heal.red.400
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
