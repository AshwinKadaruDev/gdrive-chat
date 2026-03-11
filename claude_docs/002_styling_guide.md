# Tenex Chat Agent — Styling Guide

> A drive-connected AI chat agent for reading files and answering questions.
> Visual identity derived from [tenex.co](https://www.tenex.co/).

---

## 1. Color Palette

### Core Tokens

| Token                  | Hex         | RGB                  | Usage                                                  |
| ---------------------- | ----------- | -------------------- | ------------------------------------------------------ |
| `--color-black`        | `#000000`   | `rgb(0, 0, 0)`      | Primary background, input field backgrounds             |
| `--color-white`        | `#FFFFFF`   | `rgb(255, 255, 255)` | Headings, user message text, primary buttons            |
| `--color-yellow`       | `#FFE501`   | `rgb(255, 229, 1)`  | Brand accent — highlights, active states, key info      |
| `--color-cream`        | `#F0EEE5`   | `rgb(240, 238, 229)` | Body / paragraph text, assistant message text           |
| `--color-gray`         | `#AAAAAA`   | `rgb(170, 170, 170)` | Muted text — timestamps, metadata, placeholders         |
| `--color-border`       | `#D9D9D9`   | `rgb(217, 217, 217)` | Subtle dividers, card borders                           |
| `--color-surface-dark` | `#111111`   | `rgb(17, 17, 17)`   | Elevated surfaces — chat bubbles, cards, side panels    |
| `--color-surface-mid`  | `#1A1A1A`   | `rgb(26, 26, 26)`   | Input bar background, secondary surfaces                |

### Semantic Aliases

```css
:root {
  /* Backgrounds */
  --bg-app:            var(--color-black);
  --bg-chat-area:      var(--color-black);
  --bg-input:          var(--color-surface-mid);
  --bg-sidebar:        var(--color-surface-dark);
  --bg-user-bubble:    var(--color-surface-dark);
  --bg-agent-bubble:   transparent;
  --bg-file-card:      var(--color-surface-dark);

  /* Text */
  --text-primary:      var(--color-white);
  --text-body:         var(--color-cream);
  --text-muted:        var(--color-gray);
  --text-accent:       var(--color-yellow);
  --text-on-accent:    var(--color-black);

  /* Interactive */
  --accent:            var(--color-yellow);
  --accent-hover:      #FFD600; /* slightly darker yellow on hover */
  --border-default:    rgba(255, 255, 255, 0.08);
  --border-active:     var(--color-yellow);

  /* Status */
  --status-success:    #4ADE80;
  --status-error:      #F87171;
  --status-loading:    var(--color-yellow);
}
```

### How to Apply the Yellow Accent

Yellow is the **spotlight** color — use it sparingly and intentionally to draw the eye to the most important element on screen at any moment.

**Do use yellow for:**
- The "Send" button or primary action
- Active/selected file or conversation in a sidebar
- Key data points in an answer (file name, number, date)
- Loading indicators and progress states
- The agent's "thinking" or "reading file" animation
- Inline highlights when the agent quotes directly from a file

**Don't use yellow for:**
- Large blocks of text
- Backgrounds of full sections (except small badges/tags)
- Every link or button — only the primary action


---

## 2. Typography

### Font Stack

| Role            | Font Family                               | Fallback                |
| --------------- | ----------------------------------------- | ----------------------- |
| **Display**     | `Mondwest`                                | `Arial, sans-serif`     |
| **Body / UI**   | `GT Standard L Standard`                  | `Arial, sans-serif`     |
| **Code / Files**| `JetBrains Mono` or `SF Mono`             | `monospace`             |

> **Licensing note:** If Mondwest and GT Standard are unavailable, substitute `Inter` (body/UI) and `Space Mono` or any pixelated display font for the display type.

### Type Scale

| Element                     | Font          | Size    | Weight | Color            | Letter Spacing |
| --------------------------- | ------------- | ------- | ------ | ---------------- | -------------- |
| App title / brand mark      | Mondwest      | 24px    | 400    | `--text-primary` | 0              |
| Page heading (e.g. "Chats") | GT Standard   | 20px    | 600    | `--text-primary` | -0.01em        |
| Agent response body         | GT Standard   | 15px    | 400    | `--text-body`    | 0              |
| User message body           | GT Standard   | 15px    | 400    | `--text-primary` | 0              |
| Metadata / timestamps       | GT Standard   | 12px    | 400    | `--text-muted`   | 0.02em         |
| File names in cards         | GT Standard   | 13px    | 600    | `--text-primary` | 0              |
| Code / file excerpts        | JetBrains Mono| 13px    | 400    | `--text-body`    | 0              |
| Button labels               | GT Standard   | 14px    | 500    | `--text-on-accent` or `--text-primary` | 0.02em |

### Formatting Rules

- **No all-caps** except small labels (e.g., "READING FILE…", "DRIVE CONNECTED").
- Use the yellow accent color inline within the agent's response to highlight file names, extracted values, or key terms — the same way Tenex highlights "Tenex" and "Disrupt yourself" in headings.
- Keep line-height at **1.5** for body text to maintain readability in the chat stream.


---

## 3. Layout & Spacing

### Chat Interface Structure

```
┌─────────────────────────────────────────────────┐
│  ■ Tenex Agent            [file status] [•••]   │  ← Header bar
├──────────┬──────────────────────────────────────┤
│          │                                      │
│ sidebar  │         chat messages area           │
│ (files,  │                                      │
│ history) │   ┌──────────────────────────────┐   │
│          │   │  user message (right-aligned) │   │
│          │   └──────────────────────────────┘   │
│          │                                      │
│          │   agent message (left-aligned,       │
│          │   no bubble — just text)             │
│          │                                      │
├──────────┴──────────────────────────────────────┤
│  [📎]  Type a message…                 [Send ➤] │  ← Input bar
└─────────────────────────────────────────────────┘
```

### Spacing Tokens

| Token       | Value  | Usage                                         |
| ----------- | ------ | --------------------------------------------- |
| `--space-xs`| 4px    | Inner padding in tags/badges                  |
| `--space-sm`| 8px    | Gap between inline elements                   |
| `--space-md`| 16px   | Padding inside cards, between chat messages    |
| `--space-lg`| 24px   | Section padding, sidebar gutters               |
| `--space-xl`| 32px   | Top-level container padding                    |

### Key Layout Rules

- **Chat messages:** 16px vertical gap between consecutive messages. 24px gap between different speakers.
- **User bubbles** are right-aligned, max-width 70%, with `--bg-user-bubble` background and 8px border-radius.
- **Agent responses** are left-aligned, full width, no bubble background — just text on the dark canvas. This keeps the agent feeling embedded in the interface, not boxed in.
- **Sidebar** width: 280px, collapsible. Background `--bg-sidebar` with a 1px right border of `--border-default`.


---

## 4. Components

### 4.1 Chat Bubbles

**User Message**
```css
.user-message {
  background: var(--bg-user-bubble);       /* #111111 */
  color: var(--text-primary);              /* white */
  border-radius: 8px;
  padding: 12px 16px;
  max-width: 70%;
  margin-left: auto;
  border: 1px solid var(--border-default); /* subtle white border */
}
```

**Agent Message**
```css
.agent-message {
  background: transparent;
  color: var(--text-body);                 /* cream #F0EEE5 */
  padding: 4px 0;
  max-width: 100%;
}

.agent-message strong,
.agent-message .highlight {
  color: var(--text-accent);               /* yellow #FFE501 */
}
```

### 4.2 Buttons

**Primary (Send / Main CTA)**
```css
.btn-primary {
  background: var(--color-white);
  color: var(--color-black);
  border: none;
  border-radius: 0px;                     /* sharp edges, Tenex style */
  padding: 10px 20px;
  font-family: 'GT Standard L Standard', Arial, sans-serif;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  transition: background 0.15s ease;
}

.btn-primary:hover {
  background: var(--color-yellow);
  color: var(--color-black);
}
```

**Secondary (Cancel / Subtle Actions)**
```css
.btn-secondary {
  background: transparent;
  color: var(--text-body);
  border: 1px solid var(--border-default);
  border-radius: 0px;
  padding: 10px 20px;
  font-size: 14px;
  cursor: pointer;
  transition: border-color 0.15s ease;
}

.btn-secondary:hover {
  border-color: var(--color-yellow);
  color: var(--text-primary);
}
```

### 4.3 File Cards (Drive Files)

Displayed when the agent references or lists drive files.

```css
.file-card {
  background: var(--bg-file-card);         /* #111111 */
  border: 1px solid var(--border-default);
  border-radius: 8px;
  padding: 12px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  transition: border-color 0.15s ease;
}

.file-card:hover {
  border-color: var(--color-yellow);
}

.file-card .file-icon {
  color: var(--color-yellow);              /* yellow icon for the file type */
  flex-shrink: 0;
}

.file-card .file-name {
  color: var(--text-primary);
  font-weight: 600;
  font-size: 13px;
}

.file-card .file-meta {
  color: var(--text-muted);
  font-size: 12px;
}
```

### 4.4 Input Bar

```css
.input-bar {
  background: var(--bg-input);             /* #1A1A1A */
  border-top: 1px solid var(--border-default);
  padding: 12px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.input-field {
  background: transparent;
  border: none;
  color: var(--text-primary);
  font-size: 15px;
  font-family: 'GT Standard L Standard', Arial, sans-serif;
  flex: 1;
  outline: none;
}

.input-field::placeholder {
  color: var(--text-muted);
}
```

### 4.5 Loading / Thinking State

When the agent is reading a file or generating a response, show a yellow pulsing indicator.

```css
.thinking-indicator {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--text-muted);
  font-size: 13px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.thinking-dot {
  width: 6px;
  height: 6px;
  background: var(--color-yellow);
  border-radius: 50%;
  animation: pulse 1.2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 0.3; transform: scale(0.8); }
  50%      { opacity: 1;   transform: scale(1);   }
}
```

### 4.6 Inline Source Citation

When the agent quotes or references a specific file section, highlight it with a yellow left-border.

```css
.source-citation {
  border-left: 3px solid var(--color-yellow);
  padding: 8px 12px;
  margin: 8px 0;
  background: rgba(255, 229, 1, 0.04);    /* very faint yellow tint */
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  color: var(--text-body);
  border-radius: 0 4px 4px 0;
}

.source-citation .source-label {
  color: var(--color-yellow);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 4px;
}
```

### 4.7 Sidebar — File List & Chat History

```css
.sidebar {
  background: var(--bg-sidebar);
  width: 280px;
  border-right: 1px solid var(--border-default);
  padding: var(--space-lg) 0;
  overflow-y: auto;
}

.sidebar-section-label {
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  padding: 0 var(--space-lg);
  margin-bottom: var(--space-sm);
}

.sidebar-item {
  padding: 10px var(--space-lg);
  color: var(--text-body);
  font-size: 14px;
  cursor: pointer;
  transition: background 0.1s ease;
  border-left: 3px solid transparent;
}

.sidebar-item:hover {
  background: rgba(255, 255, 255, 0.04);
}

.sidebar-item.active {
  color: var(--text-primary);
  border-left-color: var(--color-yellow);  /* yellow active indicator */
  background: rgba(255, 229, 1, 0.06);
}
```


---

## 5. Iconography & Visual Details

- **Icon style:** Line/outline icons, 1.5px stroke, white default color. Use a set like Lucide or Phosphor. Keep them small (16–20px in the UI).
- **File-type icons** should use yellow fills to pop against the dark background.
- **Arrow icons** inside buttons follow the Tenex pattern: a small ↗ or → glyph sitting inside the button, right-aligned.
- **Border radius:** `0px` for buttons (sharp, intentional). `8px` for cards and bubbles (just enough softness). `4px` for small tags/badges.
- **Dividers:** 1px solid `rgba(255, 255, 255, 0.08)` — barely visible, just enough to separate.


---

## 6. Motion & Interaction

| Interaction           | Property           | Duration | Easing         |
| --------------------- | ------------------ | -------- | -------------- |
| Button hover          | background, color  | 150ms    | ease           |
| Card hover border     | border-color       | 150ms    | ease           |
| Sidebar item hover    | background         | 100ms    | ease           |
| Message appear        | opacity, translateY| 200ms    | ease-out       |
| Thinking dots pulse   | opacity, scale     | 1200ms   | ease-in-out    |
| File card enter       | opacity, translateY| 250ms    | ease-out       |

- Keep animations minimal and fast — the interface should feel **snappy and decisive**, matching Tenex's builder energy.
- New chat messages should fade in with a slight upward slide (`translateY: 8px → 0`).
- Avoid bounce or elastic easing — this is a professional tool, not playful.


---

## 7. Theme System

The app supports **dark** (default) and **light** themes via CSS variables + Tailwind's `class` strategy.

### How it works
- `useTheme` Zustand store manages theme state, persisted in `localStorage` (`tenex-theme` key)
- Toggle button in `TopBar` (Sun/Moon icons)
- `<html>` has `class="dark"` by default; `main.tsx` applies saved theme synchronously before render
- Colors defined as CSS variables in `index.css` (`@layer base`), using space-separated RGB channels for Tailwind alpha modifier compatibility (`bg-brand-500/10`)
- Semantic tokens `--fg-primary`, `--fg-inverted`, `--border-subtle`, `--hover-overlay` adapt per theme

### CSS variable conventions
- Surface/brand/cream colors: use RGB channels (`--surface-950: 0 0 0`) → consumed via `rgb(var(--surface-950) / <alpha-value>)` in Tailwind config
- Semantic colors: use plain hex/rgba (`--fg-primary: #FFFFFF`) → consumed via `var(--fg-primary)` directly
- In components: use `text-fg-primary` instead of `text-white`, `border-[var(--border-subtle)]` instead of `border-white/[0.08]`, `bg-fg-primary` instead of `bg-white`


---

## 8. Quick Reference — Do's and Don'ts

**Do:**
- Use black as the dominant canvas — let content breathe on darkness
- Use yellow only for the one thing you want the user to notice first
- Keep buttons sharp-cornered (0px radius) for a precise, intentional feel
- Use cream (`#F0EEE5`) for agent body text — softer than pure white
- Highlight file names and extracted data in yellow within agent responses
- Use the pixelated Mondwest font only for the brand mark or splash — not in the chat UI

**Don't:**
- Use yellow backgrounds for large areas — it overwhelms
- Put more than one yellow element competing for attention in the same view
- Use rounded, bubbly aesthetics — the design language is sharp and editorial
- Add color beyond the core palette — no blues, greens, or gradients in the UI
- Use light gray text on light backgrounds — always maintain strong contrast

---

*Derived from the Tenex visual identity at tenex.co. Adapt and evolve as the product grows, but anchor every decision in: black canvas, yellow spotlight, sharp edges, warm type.*