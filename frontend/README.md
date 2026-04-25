# Overfished frontend

Next.js **16** + React **19** + Tailwind **4** web app for the Overfished demo.

## Product context

Vision, stack, team RACI, and environment variable **names** live in the repository [README.md](../README.md). Architecture notes: [../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).

## API calls

All domain and agent traffic should go through the Python BFF under [../api/](../api/), not directly from the browser to third-party fishing APIs (auth, caching, and rate limits belong server-side).

Copy `.env.example` to `.env.local` and set `NEXT_PUBLIC_API_BASE_URL` to your local or deployed API origin.

## Run locally

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Deploy

See [Next.js deployment docs](https://nextjs.org/docs/app/building-your-application/deploying).
