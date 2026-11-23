# Workflows in the Guide

The Workflows section of the Guide lists every line of enquiry Loupe supports and opens each as a step-by-step
tutorial. Guide (bottom right of a case), then **Workflows: step-by-step guides**. Area guides, Start here and some
next-step cards open a workflow directly.

- `catalogue.ts`: the list. Each workflow's title, "Use this when", the questions and kinds of case it is grouped
  under, the areas it passes through, the guidance features it shows and the switches its steps sit behind.
- `tutorials/`: each workflow's steps. A step has an instruction, what the person should see on the demo case
  ("Demo: State v. Mateo Ruiz (synthetic)"), a picture, its alt text, and the screen and control "Open this screen"
  goes to.
- `WorkflowGuide.tsx`: the list and the tutorial. `WorkflowHost.tsx` opens it on the `loupe:open-workflow` event
  (`open.ts`).
- `workflows.test.tsx`: every workflow has 4 to 12 steps; every picture exists at both widths and has a recipe;
  every anchor a step names exists; every guidance feature appears in a workflow; the navigation works.

## Pictures

Every picture comes from the live demo case, taken by a committed script. Nothing is drawn by hand. After a change to
a screen, take every picture again (signed in with the jobs login over plain http, read only):

```
cd frontend_v2
node journeys/workflow-stills.mjs
```

One picture: `--only money-cash`. One width: `--width 390`. `--dump <dir>` also writes each screen's words, to check
a step's "you should see" line against the screen. The script stops every request that would change the case and
exits 1 if any picture failed or any request was stopped.

The pictures are `public/docs/workflows/img/<shot>-1440.webp` (desktop) and `<shot>-390.webp` (phone width, cropped
to the part of the screen that matters). A step's `shot` names its recipe in `SHOTS` in the script.

When a screen changes, also read the step's words again: the numbers in "you should see" are the demo case's.

## Live check

`journeys/live-workflowguide.mjs` signs in with the jobs login and walks the section on the live site at 1440 and
390 wide, read only:

```
node journeys/live-workflowguide.mjs --out <dir> --follow money,contact,corroborate --ends --quiet
```

`--follow` walks each named workflow step by step with Next and the arrow keys and presses Open this screen on every
step; `--ends` opens every workflow's first and last step and checks every picture loads; `--quiet` checks that a
person with guidance off gets nothing opened by itself, that the area guide's links open their workflow, and that
Start here offers the workflows to a person with guidance on (answered in the browser; nothing is saved).
