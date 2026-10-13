---
name: Sales Copilot
description: A practical sales workbench for evidence review and approved CRM tasks.
colors:
  ink: "#152a36"
  muted: "#526773"
  blue: "#146174"
  blue-hover: "#104c5d"
  nav: "#132d39"
  line: "#dbe2e6"
  surface: "#fff"
  paper: "#f3f6f7"
  teal-light: "#e5f2ef"
  amber: "#725216"
  red: "#8c2727"
  input-border: "#99aab3"
  focus: "#168a9c"
  rail-text: "#ecf6f8"
  nav-text: "#c4d6dd"
  nav-hover: "#274653"
  nav-active: "#d5edf0"
  nav-active-text: "#173b48"
  secondary: "#e8eff2"
  secondary-text: "#184858"
  secondary-hover: "#d9e7ec"
  selected: "#eaf4f7"
  table-header: "#f7f9fa"
  row-line: "#eaf0f2"
  recommend-text: "#20564d"
  clarify: "#f7edda"
  clarify-text: "#694710"
  no-action: "#edf3f5"
  no-action-text: "#41606a"
  failed: "#f9e9e7"
typography:
  headline:
    fontFamily: "Arial, Helvetica, sans-serif"
    fontSize: "32px"
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: "-.025em"
  title:
    fontFamily: "Arial, Helvetica, sans-serif"
    fontSize: "19px"
    fontWeight: 700
    lineHeight: 1.3
  body:
    fontFamily: "Arial, Helvetica, sans-serif"
    fontSize: "14px"
    lineHeight: 1.55
  label:
    fontFamily: "Arial, Helvetica, sans-serif"
    fontSize: "11px"
    fontWeight: 600
    letterSpacing: ".06em"
rounded:
  status: "4px"
  control: "6px"
  brand: "9px"
  panel: "12px"
  login: "14px"
spacing:
  chip-gap: "6px"
  label-gap: "8px"
  action-gap: "12px"
  control-horizontal: "16px"
  mobile-workspace: "20px 16px"
  panel-gap: "24px"
  desktop-workspace: "25px 36px 18px"
components:
  button-primary:
    backgroundColor: "{colors.blue}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "11px 16px"
  button-primary-hover:
    backgroundColor: "{colors.blue-hover}"
  button-secondary:
    backgroundColor: "{colors.secondary}"
    textColor: "{colors.secondary-text}"
    rounded: "{rounded.control}"
    padding: "11px 16px"
  button-secondary-hover:
    backgroundColor: "{colors.secondary-hover}"
  panel-detail:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
    padding: "23px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "11px 12px"
  status-recommend:
    backgroundColor: "{colors.teal-light}"
    textColor: "{colors.recommend-text}"
    rounded: "{rounded.status}"
    padding: "5px 7px"
---

# Design System: Sales Copilot

## Overview

Sales Copilot is a practical, dense sales workbench. Its observed visual structure is a navy navigation rail beside a light workspace, with a review queue and an evidence detail panel. Teal action buttons draw attention to investigation and task review.

The shipped interface applies the product principle of evidence before action: candidate signals appear separately from investigation findings; supporting quotes and source identifiers sit alongside the proposed task. This document describes the implementation, not additional user preferences or a proposed redesign.

**Key Characteristics:**

- Compact tables and restrained Arial typography.
- White bordered panels on a pale workspace.
- Explicit decision labels, evidence references, and approval states.
- A responsive queue that retains tabular data on small screens.

## Colors

The palette combines a dark navy anchor with a muted teal action accent and cool neutral surfaces. Frontmatter values preserve the source CSS colors.

### Primary

- **Teal action (`blue`)**: primary buttons, text actions and input caret. The darker `blue-hover` indicates enabled hover.
- **Light teal (`teal-light`)**: action-proposed status and successful notices.

### Secondary

- **Amber**: clarification and scripted-demo indicators, using distinct pale backgrounds.
- **Red**: failed investigation and error text, paired with pale red backgrounds.

### Neutral

- **Navy rail (`nav`)**: persistent workspace navigation.
- **Ink / muted**: primary content versus metadata and secondary descriptions.
- **Surface / paper**: white panels versus the light workspace.
- **Line**: panel borders and structural separators.
- **Selected**: pale blue table row highlight; active navigation instead uses light teal with dark text.

## Typography

Arial, Helvetica, sans-serif is the only authored interface font stack. The implementation uses the browser monospace stack for preformatted traces and code.

- **Headline**: 32px, bold, 1.15 line height, -.025em tracking; 27px on phones.
- **Panel title**: 19px, bold, 1.3 line height.
- **Finding title**: 17px, bold; task title 14px, bold.
- **Body**: descriptions and findings generally 14px with paragraph line height 1.55. Table cells use 13px.
- **Metadata**: 10–12px for citations, signals, priority and dates.
- **Table label**: 11px, 600 weight, uppercase, .06em tracking.
- **Numbers**: currency and dates use tabular numerals where authored.

## Layout

Desktop uses a 214px sticky rail with full viewport height. The main workspace has a maximum width of 1800px and padding of 25px 36px 18px. The queue/detail grid uses `minmax(0,1.5fr) minmax(310px,1fr)` with a 24px gap. The detail panel is sticky at 20px from the top.

At widths above 1500px, horizontal workspace padding grows to 48px and the detail minimum becomes 380px. At 1150px and below, the rail narrows to 176px, workspace padding becomes 24px, the queue and detail stack, and detail positioning becomes static.

At 650px and below, the rail becomes a full-width header with horizontally scrollable navigation; the profile/sign-out area is hidden. Workspace padding becomes 20px 16px, the toolbar stacks, and panel gaps become 18px. The queue table retains a 470px minimum width inside a scroll area capped at 450px high. Selecting an opportunity scrolls to its detail panel, whose scroll margin is 16px.

## Elevation & Depth

The workbench uses tonal layering and 1px borders rather than panel shadows. The sign-in card is the exception: `0 10px 50px #17374712` gives it a soft shadow against the page. Selection, navigation and status colors convey state without lifting surfaces.

## Shapes

Controls use 6px corners, panels 12px, status and signal chips 4px, the brand mark 9px and the login card 14px. Panels use thin cool-gray borders; evidence quotes use a single left rule. Tables preserve square internal rows within rounded outer containers.

## Components

### Buttons

Primary buttons use teal, white text, 11px 16px padding and 600 weight. Secondary investigation buttons use pale blue-gray and dark teal text. Text actions have transparent backgrounds and a pale hover fill. Background transitions last .16s with ease timing. Disabled buttons have .6 opacity and a wait cursor. Full-width variants support investigation and final confirmation.

### Inputs

White fields have a 1px `input-border` stroke, 6px corners and 11px 12px padding. Search labels sit above the field. Password entry uses a visible label and standard autocomplete semantics.

### Navigation

The desktop rail uses muted light text, a darker hover surface and pale teal active state. Current navigation is exposed with `aria-current`. The tasks entry can show a count badge. Phone navigation remains horizontally scrollable.

### Queue and status

The review queue presents account/stage, value and review signal. Selection is communicated by the pale selected row and the account button's pressed state. Search filters account or stage. Status text explicitly distinguishes action proposed, input needed, no action and investigation failure; color supplements those labels.

### Evidence detail

The detail panel shows opportunity facts, candidate signals, investigation controls, decision, priority, proposed task and supporting quotes. Citations carry note identifiers. CRM notes and tool activity use native disclosure controls; raw notes start expanded before a decision exists. Preformatted traces wrap long content and scroll within a 440px maximum height.

### Approval and feedback

Task creation follows Review task → exact-task confirmation → Confirm and create task. Dismiss and Back to review are separate controls. Resolved proposals show Task created or Proposal dismissed. Loading uses a spinner and status text; notices use `role="status"`, errors use `role="alert"`. Empty tables explain the next available step.

### Focus and motion

Buttons, links, inputs and summaries use a 3px `focus` outline with 4px offset. The spinner rotates linearly once per second. Reduced-motion preference disables authored animation and transitions.

## Do's and Don'ts

### Do

- **Do** retain visible evidence quotations, source identifiers and separate approval controls.
- **Do** keep numeric columns readable with tabular numerals and horizontal queue scrolling on phones.
- **Do** pair state colors with explicit labels and retain visible keyboard focus.
- **Do** use white bordered surfaces and the observed compact type hierarchy for new workbench panels.

### Don't

- **Don't** treat candidate-rule signals as established risk; the interface explicitly distinguishes detection from investigation.
- **Don't** collapse task review and final confirmation into a single automatic creation step.
- **Don't** obscure traces, error details or scripted-demo mode labels.
