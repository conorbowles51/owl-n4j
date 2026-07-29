# Loupe landing site

Standalone public brochure site for Loupe. It is intentionally isolated from `frontend_v2` so it can be hosted and released independently.

## Direction

The visual concept is an **evidence-led case room**: fragmented signals assemble around a living 3D Loupe lens, resolve into one persistent case model, and move through real product views into durable findings. The narrative is grounded in Loupe's live use on serious fraud and criminal casework, while remaining useful to the wider investigations market.

## Run locally

```bash
npm install
npm run dev
```

Production build:

```bash
npm run build
```

## Contact configuration

Copy `.env.example` to `.env` if you need to override `VITE_CONTACT_EMAIL`, which defaults to `sales@loupe.ie`. The walkthrough form prepares an email draft in the visitor's default email client; it does not send or retain form data itself.

## Performance and accessibility

- Three.js rendering pauses when the hero is off-screen or the tab is hidden.
- Device pixel ratio is capped to reduce GPU load.
- `prefers-reduced-motion` receives a static composed 3D frame and disables decorative motion.
- The product content remains fully understandable without WebGL.
- Navigation, modal focus management, semantic landmarks and visible keyboard focus are included.
