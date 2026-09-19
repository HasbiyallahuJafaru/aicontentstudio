# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

(Desktop app: Electron window rendering a React UI. Windows first; macOS/Linux later.)

## Stack

Electron + React + TypeScript + Vite + Tailwind CSS (apps/desktop), Python 3.12 backend (apps/backend), SQLite via
stdlib `sqlite3`, FFmpeg. Electron and Python talk over stdin/stdout JSON lines. Decided with the user 2026-09-19;
full rationale in `DECISIONS.md`.

## Users

One person: the owner/operator, producing up to six social posts a day for their own channels. No accounts, teams,
or billing. They sit at a Windows desktop for a production session: brief a batch, wait for renders, review, fix
what's off, approve, export to Metricool.

## Product Purpose

A local content production studio: turn a short brief (topic, tone, format, quantity, platforms) into finished,
premium 9:16 videos and 4:5 images with quote, narration, visuals, palette, audio and per-platform metadata, then
export them in organized folders. Success = a batch of six distinct, non-repetitive, publish-ready pieces without
touching technical settings. Spec: `Prd.txt`.

## Positioning

Not a scheduler, not a chat box with a Generate button. AI decides the creative (structured JSON from DeepSeek);
deterministic local software does everything measurable: visual analysis, palette, layout, rendering, validation.
Repetition is treated as an engineering problem (quote, asset, palette and layout histories).

## Operating Context

Long-running local jobs (search, download, analysis, TTS, FFmpeg) while the UI stays responsive with real stage
progress. Media stays on disk; SQLite stores paths. Works offline for browsing, editing, re-rendering and exporting
existing projects. Output goes to an external scheduler (Metricool) by folder export.

## Capabilities and Constraints

- Core flow: Create → brief → content generation → visual selection → analysis → design → narration → render →
  preview → review/regenerate one component → approve → export.
- Providers behind interfaces: DeepSeek, Pexels, Unsplash, local open-source TTS.
- API keys never reach the renderer process; never logged.
- Preview and export are driven by the same design spec.
- Out of scope: publishing, scheduling, timeline editor, cloud anything, auth.

## Brand Commitments

Name: **AI Social Content Studio**. Should read as serious professional creative software (Recordly is the UX quality
reference): premium, quiet, precise, editorial, technical, confident. Explicitly not a generic AI SaaS dashboard, no
purple AI gradients, neon, glassmorphism, oversized rounded cards or metric-card walls.

## Evidence on Hand

None yet: no logo, fonts, music library or sample renders. Do not fabricate usage numbers or example content presented
as real.

## Product Principles

1. The canvas (preview of the actual output) is the centre of every screen; controls are small and secondary.
2. Automation over configuration; advanced settings are progressive disclosure.
3. Progress is honest: stages map to real pipeline steps, never fake percentages.
4. Regenerate the smallest thing that changed.
5. Coherent variety over random variation.

## Accessibility & Inclusion

Keyboard navigation and shortcuts, visible focus, accessible labels, WCAG AA contrast, reduced-motion support.
