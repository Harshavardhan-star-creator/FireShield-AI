# Fire and smoke model weights

The project includes `fire_smoke_yolo.pt` at the default path. The app validates its runtime class names before enabling inference; this check confirms labels, not model quality or safety suitability.

## Expected model contract

- **Default file:** `models/fire_smoke_yolo.pt` at the project root.
- **Override:** set `FIRESHIELD_FIRE_SMOKE_MODEL` to an absolute path, or a path relative to the project root.
- **Format/runtime:** Ultralytics-compatible YOLO `.pt` weights, loaded through `ultralytics.YOLO`.
- **Required classes:** both `fire` (the alias `flame` is also accepted) and `smoke`, matched case-insensitively.
- **Class IDs:** the app reads IDs from `model.names` and maps by class name, so IDs are not hard-coded. For the conventional two-class layout use ID `0` for `fire`/`flame` and ID `1` for `smoke`; another ordering is accepted when the names are correct.
- **Inference device:** CPU is explicitly selected by default. The integration passes `device="cpu"` to Ultralytics and does not require CUDA.

## Enable real inference

1. Start the app and check whether the included weights pass the runtime class-name validation.
2. To use different weights, set `FIRESHIELD_FIRE_SMOKE_MODEL` to an absolute path, or a path relative to the project root.
3. Install dependencies with `python -m pip install -r requirements.txt` and restart Streamlit.
4. Review model provenance and validate it for your intended use. This app checks that weights load and expose the required labels; it cannot establish training quality or safety certification.

Generic pretrained YOLO weights do not qualify unless they were trained with both required classes. Missing files, unavailable Ultralytics, load errors, or incompatible class names are reported as detection unavailable. Without compatible weights, uploaded images and webcam captures can be previewed with OpenCV, but detection stays unavailable and no detections or confidence scores are shown.
