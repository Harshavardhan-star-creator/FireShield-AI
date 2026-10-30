# FireShield AI

**FireShield AI – AI-Enabled Autonomous Fire Detection, Risk Prediction and Intelligent Fire Suppression System for Industrial Facilities** is a college project prototype built with Python and Streamlit.

## Current modules

- **Dashboard** — facility overview with clearly labeled simulated example readings.
- **Sensor Monitoring** — scenario-based simulated sensor readings, health indicators, charts, and recent history.
- **Camera Monitoring** — JPG/JPEG/PNG upload or one-shot browser webcam capture, plus Start/Stop continuous browser webcam monitoring with sampled CPU YOLO inference, annotated video frames, confidence scores, deduplicated alerts, and recent detection history.
- **Local event storage** — SQLite history at `data/fireshield.db` for sensor readings, camera detections, risk assessments, decisions, virtual suppression events, and operator overrides. Recent records are restored on application start; if SQLite is unavailable, the session continues with in-memory data.

A YOLO weights file is present at the default path. Camera inference is available only if it loads successfully and passes runtime validation for both fire and smoke class names. Continuous monitoring uses `streamlit-webrtc` and browser camera permission; local access requires localhost, while remote deployments require HTTPS and working STUN/TURN connectivity. Camera detections enter the existing recent-event risk evidence path and do not trigger physical suppression.

## Run locally

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Install dependencies and run:

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

Open the local URL printed by Streamlit, usually `http://localhost:8501`.

## Optional fire/smoke model

The app looks for `models/fire_smoke_yolo.pt`. Alternatively, set `FIRESHIELD_FIRE_SMOKE_MODEL` to a YOLO weights path. The model must be trained for both fire and smoke and expose class names `fire` or `flame`, and `smoke`. Generic pretrained YOLO models are rejected if those classes are absent. See [models/README.md](models/README.md) for details.

Even with a model, class-name validation does not certify its quality. This prototype is not production-ready and must not be used for real fire-safety decisions. No physical suppression hardware control is implemented.
