# Loupe landing site

Standalone public brochure site for Loupe. It is intentionally isolated from `frontend_v2` so it can be hosted and released independently.

## Direction

The site is built around a film-led product story. The full product film follows the hero, then five shorter Remotion films demonstrate evidence processing, comprehensive source-linked summaries, cross-case text search, case views, and AI-assisted investigation. Each feature film is paired with concise product copy and uses interfaces modelled on the running Loupe application.

## Run locally

```bash
npm install
npm run dev
```

Production build:

```bash
npm run build
```

## Film assets

Optimized MP4, WebM, and poster assets live in `public/films`. Keep both video formats when replacing a film so browsers can choose the most suitable source. Feature films are loaded only as they approach the viewport, and playback pauses while they are off-screen.

The editable Remotion compositions live in the separate `loupe-product-film-motion` project. Re-render a composition there, optimize it for the web, then copy the updated video and poster files into `public/films` without changing their public filenames.

## Contact configuration

Copy `.env.example` to `.env` if you need to override `VITE_CONTACT_EMAIL`, which defaults to `sales@loupe.ie`. The walkthrough form prepares an email draft in the visitor's default email client; it does not send or retain form data itself.

## Performance and accessibility

- Below-the-fold films defer their video sources until they approach the viewport.
- Off-screen films pause automatically.
- `prefers-reduced-motion` disables autoplay and decorative motion.
- Navigation, modal focus management, semantic landmarks, descriptive video labels, and visible keyboard focus are included.
- The site remains fully understandable from its copy and poster imagery without video playback.
