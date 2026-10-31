# Run the backend on another computer with ngrok

Use this when you want to change and run the backend on another computer
(for example your personal laptop) and have the app use it from anywhere.

## The idea in one minute

Think of the ngrok address as a **phone number**:

```
https://lend-shadily-cresting.ngrok-free.dev
```

- The app always calls this same number (it is in the app's `.env`).
- Whichever computer is running ngrok **answers the call**.
- Only **one computer at a time** can hold the number.

So you never change anything in the app. You just choose which computer answers.

> Each computer keeps its **own saved data** (users, scan history, favorites),
> like a separate notebook. Data on the Mac does not appear on the laptop.

---

## Part 1: One-time setup on the laptop

Do this only once.

### 1. Install the tools
- **Docker Desktop** (open it and leave it running)
- **Git**
- **ngrok**:
  ```bash
  brew install ngrok
  ```

### 2. Log ngrok in to your account
1. Go to https://dashboard.ngrok.com and log in with **personal.devaccnt@gmail.com**
   (the account that owns the domain above).
2. Open **Getting Started → Your Authtoken** and copy the token.
   (Not the "API Keys" page: that is something different.)
3. Run:
   ```bash
   ngrok config add-authtoken <paste-token-here>
   ```
   It should say `Authtoken saved to configuration file`.

The token is saved inside ngrok's own settings on the laptop. **Never put the
token in this repo, a `.env` file or a note**: it works like a password.

### 3. Get the backend code
```bash
git clone https://github.com/Jasam-Abdulsalam/scanrix-backend.git
cd scanrix-backend
git checkout dev
```

### 4. Create the backend `.env`
`.env` is not in git, so the laptop needs its own.
The easiest way: copy the `.env` file from the Mac to the laptop privately
(AirDrop, USB drive). Do **not** send it through git, chat or email: it holds
secret keys.

Or create it from scratch: `cp .env.example .env` and fill it in as described in
[RUN_ON_NEW_MACHINE.md](RUN_ON_NEW_MACHINE.md), step 2.

### 5. Start the backend and load the data
Follow [RUN_ON_NEW_MACHINE.md](RUN_ON_NEW_MACHINE.md), **step 3** (start) and
**step 4** (load the data). The laptop's database starts empty, so step 4 is needed.

Check it works:
```bash
curl http://localhost:8000/health
```
You should see `{"status":"healthy"}`.

---

## Part 2: Every time you work on the laptop

### 1. Stop ngrok on the Mac
In the Mac terminal where ngrok is running, press **Ctrl+C**.
(If you skip this, the laptop's ngrok will fail with an "already online" error.)

### 2. Get the latest code and start the backend (on the laptop)
```bash
cd scanrix-backend
git pull origin dev
docker compose up -d --build app
```
`--build` puts your latest code changes into the running backend.
Run the same command again after every code change you want to test.

### 3. Start ngrok (on the laptop)
```bash
ngrok http 8000 --url https://lend-shadily-cresting.ngrok-free.dev
```
Wait for `Session Status: online`. **Keep this terminal open**: closing it
closes the connection.

### 4. Open the app
Nothing to change in the app. Open it (or restart it) and it now uses the laptop.
The first time, **sign up or log in again**: the laptop has its own data.

To see every request the app makes, open http://127.0.0.1:4040 on the laptop.

---

## Switching back to the Mac
1. On the laptop: press **Ctrl+C** in the ngrok terminal.
2. On the Mac: start ngrok again with the same command:
   ```bash
   ngrok http 8000 --url https://lend-shadily-cresting.ngrok-free.dev
   ```

## Keeping both computers in sync
- Made changes on the laptop? `git push`, then `git pull` on the Mac (and the other way round).
- After pulling on either computer, rebuild: `docker compose up -d --build app`.

---

## If something goes wrong

| What you see | What it means | Fix |
|---|---|---|
| `ERR_NGROK_107` / "authtoken ... is invalid" | Wrong or reset token | Copy the token again from **Your Authtoken** and re-run `ngrok config add-authtoken ...` |
| "endpoint is already online" | ngrok is still running on the other computer | Press Ctrl+C there, then try again |
| App can't connect at all | ngrok or the backend isn't running | Check `curl http://localhost:8000/health`, and that ngrok shows `online` |
| The address shows a 404 in the browser | ngrok isn't running on any computer | Start ngrok |
| My code change doesn't show up | The backend is running old code | `docker compose up -d --build app` |
| Login works on the Mac but not the laptop | Each computer has its own users | Sign up again on the laptop |

## Good to know
- The computer running the backend must stay **on and awake** while you test.
- Requests travel through ngrok's servers, so they are a bit slower than local Wi-Fi.
- The free plan has monthly limits on traffic. Normal testing won't come close.
- Anyone who knows the address can reach the backend (it still needs a login).
  Don't post the address publicly.
