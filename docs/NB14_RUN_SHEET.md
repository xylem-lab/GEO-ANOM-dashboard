# Notebook 14: run sheet (labelling)

Branch `research/accuracy-assessment-2026-11-05`. Notebook `notebooks/14_accuracy_assessment.ipynb`.
Interpreters read `docs/TASK1_LABELLING_GUIDE.md` first.

## Umesh (UA): calibration and pilot, in VS Code

1. `git checkout research/accuracy-assessment-2026-11-05` and `git pull`.
2. Open notebook 14. Kernel: Python 3.9 (`/Library/Developer/CommandLineTools/usr/bin/python3`).
3. In **Settings**, set `INTERPRETER = "UA"`. Leave `INTERPRETERS = ["UA", "Monica"]`.
4. Run, top to bottom: **Setup**, **Settings**, **1. Frames** (2 cells), **2. Draw the sample**
   (2 cells; it only loads the saved sample), **2b. v1.2 addendum** (1 cell; see below).
5. **3. Calibration**: run the first code cell. 30 photos with buttons. Label all 30.
6. **4. Pilot**: run the first code cell. 75 photos. Label all 75.
7. Stop there: don't run 5, 5b, 6 or 6b until the pilot passes the kappa check (step 4's second cell).

Photos stream from Planetary Computer: ~5–10 s for the first one, then the next ones load while you
look. If you stop, rerun the same cell: it skips what you've labelled.

**Step 2b and the footprints.** Calibration and pilot don't need it. Until the Microsoft footprint
file is downloaded (`DOWNLOAD_FOOTPRINTS = True`, once, 57 MB), 2b prints "addendum not drawn
yet" and that's expected. The v1.2 objects (5b) and **every** square (6, 6b) wait for it, because the
squares must show the footprint candidates. Draw it before anyone labels a v1.2 item; the notebook
refuses otherwise.

## Where the labels go

`Task1_results/accuracy_v1/labels/labels_ua.csv` and `labels_monica.csv` on the shared drive
(`AIM-GEO-ANOM`). Append-only: every click is a row; the latest label per item counts. Never edit
them by hand and never put them in git (they name places).

## Monica

1. Needs access to the `AIM-GEO-ANOM` shared drive.
2. Opens notebook 14 with the **Open in Colab** badge (it already points to this branch), runs
   **Setup** (allow Drive), sets `INTERPRETER = "Monica"` (exactly), runs Settings, 1, 2 and 2b.
3. **3. Calibration**: 30 photos. Then, together with UA, run the second cell of step 3: it lists
   the items where you disagree. Discuss them. If the guide/protocol wording is the problem, the
   protocol gets a new version before the pilot.
4. **4. Pilot**: 75 photos, on her own.
5. Run the second cell of step 4 (the gate). **Kappa ≥ 0.8** → both go on with 5, 5b, 6, 6b.
   **Below 0.8** → stop; the protocol is revised and the pilot is replaced from the reserve
   (`PILOT_FAILED = True`). Never relabel the same pilot photos.

## After both finish

Steps 7 (agreement), 8 (adjudication: decide each disagreement together with
`A.adjudicate(...)`, giving a reason), 9 (estimates). Then rewrite "What this shows" from the outputs.
