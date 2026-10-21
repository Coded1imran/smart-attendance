# Smart Attendance (AttendAI) - AI-Powered Attendance Management System

A production-grade, anti-proxy attendance verification web system built for hackathons and academic institutions. 

**AttendAI** prevents ghost check-ins and proxy attendance by enforcing a strict 5-layer verification pipeline combining **rotating cryptographic classroom codes**, **Haversine GPS geofencing**, **MediaPipe facial liveness challenges**, and **facial biometric feature vector matching**.

---

## 📸 Key Features & UI Screens (12 Screen Complete MVP)
1. **Landing Page (`/`)**: Hero section, value propositions, feature highlights, and role navigation.
2. **Student Registration (`/register/student`)**: Captures legal details, matriculation number, biometric consent, and a live webcam selfie (extracts mathematical embedding; raw photos are immediately destroyed).
3. **Lecturer Registration (`/register/lecturer`)**: Staff ID and credential setup for academic instructors.
4. **Login (`/login`)**: Role-selective authentication (Student vs Lecturer) issuing secure HTTP-only JWT cookies.
5. **Student Dashboard (`/student/dashboard`)**: Metric cards (Enrolled Courses, Overall Attendance %, Total Sessions), course cards with live session status, and recent history.
6. **Mark Attendance Wizard (`/student/mark-attendance`)**: 5-step anti-proxy verification pipeline:
   - Step 1: 6-digit rotating code entry.
   - Step 2: High-accuracy HTML5 GPS geofence check.
   - Step 3: Interactive liveness challenge (natural blink or head-turn prompt).
   - Step 4: Facial biometric similarity match (cosine distance).
   - Step 5: Verification receipt and status badge.
7. **Lecturer Dashboard (`/lecturer/dashboard`)**: Total Courses, Active Sessions, Total Students, and real-time attendance feed.
8. **Start Attendance Session (`/lecturer/sessions/create`)**: Classroom GPS capture, duration slider, radius configuration, and 30-second live rotating code preview.
9. **Live Attendance Monitor (`/lecturer/sessions/{id}/live`)**: Real-time projector code display (expires every 30s), auto-refreshing attendee table (5s polling), and CSV exporter.
10. **Student Attendance History (`/student/history`)**: Filter by course and date range, with verification confidence scores and progress indicators.
11. **Flagged Record Review Modal**: Enables lecturers to inspect borderline scores or location offsets and approve or reject entries.
12. **Mobile Responsive View**: Bottom navigation bar and adaptive layout for mobile devices.

---

## 🛡️ Anti-Proxy Decision Logic

| Check | Passing Criteria | Borderline Criteria | Rejection Criteria |
|---|---|---|---|
| **1. Session & Enrollment** | Session is open and student is enrolled | — | Session expired or student not enrolled |
| **2. Rotating Code** | Exact match with current 30s HMAC window | Tolerates $\pm 1$ window (30s latency buffer) | Invalid or mismatched 6-digit code |
| **3. Geolocation** | $\text{Distance} \le \text{Radius}$ | $\text{Radius} < \text{Distance} \le \text{Radius} + 15\text{m}$ | $\text{Distance} > \text{Radius} + 15\text{m}$ |
| **4. Liveness Challenge** | Eye Aspect Ratio (EAR) blink or head yaw verified | — | Challenge failed or timeout |
| **5. Face Biometric Match** | Similarity $\ge 75.0\%$ | $60.0\% \le \text{Similarity} < 75.0\%$ | Similarity $< 60.0\%$ |
| **Final Decision** | **Present** (Green) | **Pending Review / Flagged** (Yellow/Red) | **Rejected** (Red, logged to DB) |

*Duplicate prevention is enforced at both the database level via a composite unique constraint `(session_id, student_id)` and in API logic.*

---

## 🚀 Setup & Run Instructions

### 1. Prerequisites
- Python 3.10 to 3.15
- A modern web browser with camera and GPS permissions enabled (Chrome, Edge, Firefox, Safari)

### 2. Installation
Clone or navigate to the project directory:
```bash
cd C:\Users\HomePC\.gemini\antigravity\scratch\smart_attendance
```

Install requirements:
```bash
pip install -r requirements.txt
```

### 3. Seed Demo Data
Populate demo courses, active sessions, and pre-configured accounts:
```bash
python seed.py
```

### 4. Start the Application
Run the FastAPI development server:
```bash
python run.py
```
Or with uvicorn directly:
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Open your browser to:
- **Web Application**: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **Interactive Swagger Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 🔑 Pre-Seeded Demo Credentials

| Role | Email | Password | Identifier |
|---|---|---|---|
| **Lecturer** | `dr.bello@university.edu` | `password123` | Staff ID: `STF/2024/01` |
| **Student** | `ahmed.musa@student.edu` | `password123` | Matric: `U/2021/001` |
| **Student** | `fatima.ali@student.edu` | `password123` | Matric: `U/2021/002` |
| **Student** | `usman.ibrahim@student.edu` | `password123` | Matric: `U/2021/028` |

---

## ⚠️ Known Limitations & Future Improvements
1. **GPS Drift Indoors**: Standard browser HTML5 Geolocation relies on Wi-Fi/cellular triangulation indoors, which can occasionally have an error margin of 10–30 meters. The system accommodates this via a 15-meter borderline tolerance buffer that flags records for lecturer manual review rather than rejecting them immediately. In production, Bluetooth Low Energy (BLE) beacons or Wi-Fi BSSID matching could be integrated.
2. **Lighting Variations**: Severe backlighting or dim lecture halls can lower facial similarity scores. The borderline review state protects students under poor lighting conditions.
3. **WebSocket Scaling**: The current live feed utilizes 5-second polling; for auditoriums with 1,000+ simultaneous students, migrating to full Redis pub/sub WebSockets is recommended.
4. **Hardware-Backed Biometrics**: WebAuthn / FIDO2 device attestation could be combined with face matching for high-stakes examinations.
