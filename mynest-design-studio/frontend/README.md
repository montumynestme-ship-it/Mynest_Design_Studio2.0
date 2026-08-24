# Frontend — MyNest Design Studio

React + TypeScript + Vite.

## Setup

```bash
npm install
cp .env.example .env
npm run dev
```

App runs at http://localhost:5173.

## Scripts

| Script | Description |
|--------|-------------|
| `npm run dev` | Start the Vite dev server |
| `npm run build` | Type-check and build for production |
| `npm run preview` | Preview the production build |
| `npm run type-check` | Run the TypeScript compiler without emitting |
| `npm run lint` | Run ESLint over the source |

TypeScript runs in **strict mode** (see `tsconfig.json`). Linting uses ESLint's
flat config (`eslint.config.js`) with the TypeScript and React Hooks plugins.

## Structure

```
src/
├── components/   reusable UI components
├── features/     feature modules (dashboard, editor, ai, ...)
├── lib/          shared utilities & API client
├── store/        state slices
├── types/        shared TypeScript types
├── styles/       global styles
├── App.tsx       root component
└── main.tsx      entry point
```

The `@/` path alias maps to `src/`.
