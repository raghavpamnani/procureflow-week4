# Docker setup and restart verification

The image runs as UID 10001, binds application data to `/data`, and provides a healthcheck. Compose exposes the HTTP port on `127.0.0.1` only. The named volume stores business data, auth sessions and LangGraph checkpoints together.

## Deterministic demo

```sh
docker compose up --build -d
docker compose exec app python -m procureflow.accounts --home /data bootstrap-demo
docker compose exec app cat /data/demo-accounts.txt
```

The last command shows private, randomly generated credentials for your local use. Do not record them, commit them, or publish them in the video. Open http://127.0.0.1:8040 and sign in as requester. Submit a brief, then sign out and sign in as approver to review it.

To provision named accounts interactively instead of bootstrap:

```sh
docker compose exec app python -m procureflow.accounts --home /data create-user --username buyer --role requester
docker compose exec app python -m procureflow.accounts --home /data create-user --username reviewer --role approver
```

## Persisted approval demonstration

1. Submit a request and leave it awaiting approval.
2. Run `docker compose restart app`.
3. Reload, sign in if necessary, and open the saved request.
4. Confirm the same proposal fingerprint, then approve as the separate approver.

`docker compose down` keeps the named volume. Do not use `down -v` if you want to retain data.

## Actual local model in Compose

```sh
docker compose --profile local-model up -d ollama
docker compose exec ollama ollama pull qwen3:1.7b
PROCUREFLOW_MODE=ollama docker compose --profile local-model up --build -d app
```

The model service uses an internal Docker network and a separate weights volume. It publishes no model port and has cloud features disabled. CPU inference inside Docker Desktop can be slower than native Ollama using Metal on a Mac; no container inference speed is claimed.

## Automated evidence

GitHub Actions has a separate container job that builds the image, checks the non-root UID, provisions test accounts, verifies self-approval is forbidden, restarts the container during pending approval, and confirms a single order after independent approval. It uses deterministic mode and does not download a model. The local Mac does not have Docker installed; successful cloud CI is the container validation evidence.
