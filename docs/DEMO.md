# Recording preparation

The narration and exact time slots are in [VIDEO_SCRIPT.md](VIDEO_SCRIPT.md). Use actual local-model mode and show its badge. Demo mode is a separate deterministic option, explicitly labelled in the UI.

1. Follow README setup and start the cached local model server with `./scripts/serve_local_model.sh`.
2. Choose a fresh workspace, for example `.runtime/recording-02`. Run `PROCUREFLOW_HOME=.runtime/recording-02 ./scripts/python.sh -m procureflow.accounts bootstrap-demo`. Read its private credentials file locally; never commit or show it on camera.
3. Start `PROCUREFLOW_HOME=.runtime/recording-02 ./scripts/run_local.sh`. Sign in as requester. Keep the same command prepared for the restart segment.
4. Use ten laptops, 32 GB RAM, 512 GB storage, INR 900000 budget, 14-day delivery, Best value. Enable the single simulated timeout if demonstrating recovery.
5. Prepare revision history before the timed segment if showing semantic compaction: add discussion about three-year warranty and Saturday delivery across revisions. The recent-turn limit is four; compaction appears when older turns exist. Stay within the four-revision limit. Do not claim compaction from a single initial request.
6. Show requester approval controls disabled. After reviewing the revised proposal, sign out and sign in as the separate approver. Confirm the displayed amount and show the receipt.
7. Open `docs/validation/real-model-evaluation.json` and the latest green GitHub checks for the closing evidence. Only claim checks that have passed.

Rehearse at normal speaking speed. Startup and inference may need transparent edits to fit two minutes. All orders are simulated. Checkpoint branches create new requests requiring fresh approval; they do not reverse existing orders.

The script is ready; a video recording and its share link remain separate submission artifacts.
