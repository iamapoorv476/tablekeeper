# Vapi Setup — Day 2

## 1. Account setup
1. Sign up at vapi.ai, grab your **Private API Key** from Dashboard -> API Keys.
2. Dashboard -> Billing -> set a **$20 spending cap**.
3. Dashboard -> Phone Numbers -> Buy a number (pick any available number; free
   trial credit covers this for testing).

## 2. Deploy the backend first
Your Vapi assistant needs a live `serverUrl` to call. Deploy `backend/` to
Railway before creating the assistant:

```bash
railway login
railway init
railway up
railway variables set DATABASE_URL="<your Supabase session pooler URL>"
```

Copy the Railway-assigned URL (e.g. `https://tablekeeper-backend.up.railway.app`).

## 3. Update the assistant config
In `vapi/assistant-config.json`, replace: