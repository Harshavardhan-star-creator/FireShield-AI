# 🔥 FireShield AI

### AI-Enabled Autonomous Fire Detection, Risk Prediction and Intelligent Fire Suppression System for Industrial Facilities

FireShield AI is an AI-powered fire safety monitoring prototype designed to detect fire and smoke, assess potential fire risks, and initiate intelligent virtual suppression responses.

The system combines computer vision, sensor-based monitoring, risk prediction, and automated decision-making in a centralized Streamlit dashboard.

---

## 🎯 Problem Statement

Traditional fire safety systems often depend on standalone smoke detectors and manual monitoring. These systems may provide limited contextual information about fire conditions and risk levels.

FireShield AI demonstrates an integrated approach that combines camera-based fire detection, sensor monitoring, and risk assessment to support faster and more informed responses.

## ✨ Key Features

* **🔥 AI-Based Fire Detection:** Uses a YOLO-based model to identify fire and smoke.
* **📷 Live Camera Monitoring:** Continuously processes webcam frames using Streamlit WebRTC.
* **🌡️ Sensor Monitoring:** Displays simulated environmental sensor readings.
* **📊 Risk Prediction:** Evaluates fire risk using available sensor and camera events.
* **🤖 Intelligent Decision Engine:** Determines suitable responses based on assessed risk.
* **🚨 Virtual Fire Suppression:** Demonstrates automated suppression decisions without controlling physical equipment.
* **📁 Event History:** Stores and retrieves system events using SQLite.
* **🖥️ Interactive Dashboard:** Provides centralized monitoring through Streamlit.

## 🏗️ System Workflow

1. Camera captures live video frames.
2. YOLO model processes frames to detect fire and smoke.
3. Sensor monitoring collects environmental readings.
4. Risk prediction engine evaluates available inputs.
5. Decision engine determines the appropriate response.
6. Virtual suppression controller demonstrates the response.
7. Dashboard displays alerts, risk levels, and system activity.
8. Event information is stored in the SQLite database.

## 🛠️ Technologies Used

| Technology       | Purpose                      |
| ---------------- | ---------------------------- |
| Python           | Core application development |
| Streamlit        | Interactive dashboard        |
| YOLO             | Fire and smoke detection     |
| OpenCV           | Image processing             |
| Streamlit WebRTC | Live webcam streaming        |
| SQLite           | Event history storage        |
| NumPy            | Numerical operations         |

## 📂 Project Structure

```text
FireShield-AI/
│
├── app.py
├── requirements.txt
├── README.md
│
├── fireshield/
│   ├── camera_monitoring/
│   ├── dashboard/
│   ├── database/
│   ├── decision_engine/
│   ├── risk_prediction/
│   ├── sensor_monitoring/
│   ├── suppression_control/
│   ├── system_health/
│   └── zone_management/
│
├── models/
│   ├── fire_smoke_yolo.pt
│   └── README.md
│
├── test_results/
│
└── tests/
```

## ⚙️ Installation and Setup

### 1. Clone the repository

```bash
git clone https://github.com/Harshavardhan-star-creator/FireShield-AI.git
```

### 2. Navigate to the project directory

```bash
cd FireShield-AI
```

### 3. Create a virtual environment

```bash
python -m venv .venv
```

### 4. Activate the environment (Windows)

```bash
.venv\Scripts\activate
```

### 5. Install dependencies

```bash
pip install -r requirements.txt
```

### 6. Run the application

```bash
streamlit run app.py
```

The dashboard will open in your browser.

**Note:** Allow camera access in your browser when using live camera monitoring.

## 🧪 Testing

The project includes test cases covering:

* Database operations
* Decision engine
* Risk prediction engine
* Suppression control
* System health
* Workflow integration

Sample fire and smoke images, along with annotated detection outputs, are available in the `test_results/` directory.

## 🔮 Future Scope

* Integration with real industrial IoT sensors.
* Support for multiple industrial CCTV cameras.
* Deployment on edge computing devices.
* Integration with certified physical fire suppression systems.
* Advanced fire-risk prediction using historical datasets.
* Mobile notifications and remote monitoring.

## ⚠️ Project Disclaimer

FireShield AI is an educational demonstration prototype.

Sensor readings are simulated, and fire suppression actions are virtual. The project is not connected to certified industrial fire safety equipment and must not be used as a replacement for real fire detection or suppression systems.

## 👨‍💻 Developed By

**Harshavardhan**

B.Tech Student

---

⭐ If you find this project interesting, consider giving the repository a star!
