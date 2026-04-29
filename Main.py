from flask import Flask, render_template, request, session, jsonify
from flask import redirect, url_for
from flask_socketio import SocketIO
import base64
import mysql.connector
import sys, fsdk, math, ctypes, time
import cv2, threading, queue, collections
import mediapipe as mp
from ultralytics import YOLO
from datetime import datetime

app = Flask(__name__)
app.config['DEBUG'] = True
app.config['SECRET_KEY'] = '7d441f27d441f27567d441f2b6176a'

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
DB_CFG = dict(user='root', password='Sudesha79!', host='localhost', database='1drowsydb')

active_engines = {}
@socketio.on('location_update')
def handle_location(data):
    username = session.get('dname')
    engine   = active_engines.get(username)
    if engine and data:
        lat   = data.get('lat', '')
        lon   = data.get('lon', '')
        label = data.get('label', '')
        engine.location = label if label else f"{lat}, {lon}"
        print(f"Location updated for {username}: {engine.location}")

# ── PERCLOS constants ──────────────────────────────────────────────────────────
EAR_THRESHOLD  = 0.22
PERCLOS_WINDOW = 90
DROWSY_PERCLOS = 0.35
#PITCH_THRESH   = 20
#YAW_THRESH     = 35

mp_face_mesh  = mp.solutions.face_mesh
LEFT_EYE_IDX  = [33, 160, 158, 133, 153, 144]
RIGHT_EYE_IDX = [263, 387, 385, 362, 380, 373]


def _ear(landmarks, eye_idx, W, H):
    pts = [(landmarks[i].x * W, landmarks[i].y * H) for i in eye_idx]
    A = ((pts[1][0]-pts[5][0])**2 + (pts[1][1]-pts[5][1])**2) ** 0.5
    B = ((pts[2][0]-pts[4][0])**2 + (pts[2][1]-pts[4][1])**2) ** 0.5
    C = ((pts[0][0]-pts[3][0])**2 + (pts[0][1]-pts[3][1])**2) ** 0.5
    return (A + B) / (2.0 * C + 1e-6)


# ── DetectionEngine class ──────────────────────────────────────────────────────
class DetectionEngine:
    COOLDOWN     = 15
    RISK_WEIGHTS = {'drowsy': 10, 'yawning': 5, 'phone': 7, 'smoking': 7, 'distracted': 6}

    def __init__(self, session_id, username, socketio, db_cfg):
        self.session_id  = session_id
        self.username    = username
        self.socketio    = socketio
        self.db_cfg      = db_cfg
        self.frame_q     = queue.Queue(maxsize=2)
        self.running     = False
        self.ear_history = collections.deque(maxlen=PERCLOS_WINDOW)
        self._last_alert = {}
        self._yawn_ctr   = 0
        self._phone_ctr  = 0
        self._distract_ctr = 0

        self.yolo = YOLO('runs/detect/drivernew/weights/best.pt')
        self.face_mesh = mp_face_mesh.FaceMesh(
            max_num_faces=1, refine_landmarks=True,
            min_detection_confidence=0.5, min_tracking_confidence=0.5
        )
        self.location = "Unknown"
        self.last_frame = None
        self._smoke_ctr = 0
        self.frame_count = 0
        self.active_alerts = set()

    def start(self):
        self.running = True
        threading.Thread(target=self._capture_loop,   daemon=True).start()
        threading.Thread(target=self._inference_loop, daemon=True).start()

    def stop(self):
        self.running = False
        self._update_session_end()

    def _capture_loop(self):
        cap     = cv2.VideoCapture(0)
        cap.set(3, 640)
        cap.set(4, 480)
        frame_n = 0
        while self.running:
            ok, frame = cap.read()
            if not ok:
                break
            frame_n += 1
            if frame_n % 3 != 0:
                continue
            try:
                self.frame_q.put_nowait(frame)
            except queue.Full:
                pass
        cap.release()

    def _inference_loop(self):
        while self.running:
            try:
                frame = self.frame_q.get(timeout=1)
                self.frame_count += 1
                self.last_frame = frame
            except queue.Empty:
                continue

            H, W = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # ── MediaPipe — PERCLOS only (head pose removed) ──────────────────
            if self.frame_count % 2 == 0:  # run every 2nd frame to save CPU
                result = self.face_mesh.process(rgb)
                if result.multi_face_landmarks:
                    lm = result.multi_face_landmarks[0].landmark
                    ear = (_ear(lm, LEFT_EYE_IDX, W, H) +
                           _ear(lm, RIGHT_EYE_IDX, W, H)) / 2
                    self.ear_history.append(1 if ear < EAR_THRESHOLD else 0)
                    if len(self.ear_history) == PERCLOS_WINDOW:
                        perclos = sum(self.ear_history) / len(self.ear_history)
                        if perclos >= DROWSY_PERCLOS:
                            self._trigger_alert('drowsy', perclos)

            # ── YOLO — run every 3rd frame to reduce lag ──────────────────────
            annotated = frame  # default: raw frame
            if self.frame_count % 3 == 0:
                results = self.yolo(frame, conf=0.5, imgsz=320, verbose=False)

                for r in results:
                    if not r.boxes:
                        continue
                    box = r.boxes[0]
                    cls_name = self.yolo.names[int(box.cls)]
                    conf = float(box.conf)

                    if cls_name == 'awake':
                        self._yawn_ctr = max(0, self._yawn_ctr - 1)
                        self._phone_ctr = max(0, self._phone_ctr - 1)
                        self._distract_ctr = max(0, self._distract_ctr - 1)
                        self._smoke_ctr = max(0, self._smoke_ctr - 1)

                    elif cls_name == 'yawn':
                        self._yawn_ctr += 1
                        if self._yawn_ctr >= 8:
                            self._trigger_alert('yawning', conf)
                            self._yawn_ctr = 0

                    elif cls_name == 'phone':
                        self._phone_ctr += 1
                        if self._phone_ctr >= 5:
                            self._trigger_alert('phone', conf)
                            self._phone_ctr = 0

                    elif cls_name == 'smoking':
                        self._smoke_ctr += 1
                        if self._smoke_ctr >= 5:
                            self._trigger_alert('smoking', conf)
                            self._smoke_ctr = 0

                    elif cls_name == 'drowsy':
                        self._distract_ctr += 1
                        if self._distract_ctr >= 8:
                            self._trigger_alert('drowsy', conf)
                            self._distract_ctr = 0

                    elif cls_name == 'head drop':
                        # keep head drop from YOLO model but map it to distracted
                        # so no head_pose alert type is needed
                        self._distract_ctr += 1
                        if self._distract_ctr >= 6:
                            self._trigger_alert('distracted', conf)
                            self._distract_ctr = 0

                    elif cls_name == 'distracted':
                        self._distract_ctr += 1
                        if self._distract_ctr >= 6:
                            self._trigger_alert('distracted', conf)
                            self._distract_ctr = 0

                # Annotated frame only when YOLO ran
                annotated = results[0].plot() if results else frame

            # ── Stream frame to browser — runs EVERY frame, no lag ───────────
            _, buffer = cv2.imencode('.jpg', annotated,
                                     [cv2.IMWRITE_JPEG_QUALITY, 50])
            frame_b64 = base64.b64encode(buffer).decode('utf-8')
            self.socketio.emit('video_frame', {'data': frame_b64})


    def _trigger_alert(self, event_type, confidence):
        now = time.time()
        if now - self._last_alert.get(event_type, 0) < self.COOLDOWN:
            return
        self._last_alert[event_type] = now
        self.active_alerts.add(event_type)
        self.socketio.emit('alert', {
            'type':       event_type,
            'confidence': round(confidence, 3),
            'timestamp':  datetime.now().isoformat(),
            'username':   self.username
        })

        # Send email + SMS alert
        img_path = None

        if self.last_frame is not None:
            img_path = f"alert_{self.username}_{int(time.time())}.jpg"
            cv2.imwrite(img_path, self.last_frame)

        try:
            self._send_alert_email(event_type, img_path, self.location)
        except Exception as e:
            print(f"Email error: {e}")

        self._log_event(event_type, confidence)
        self._update_risk_score(event_type)
        threading.Timer(20, lambda: self.active_alerts.discard(event_type)).start()
    def _log_event(self, event_type, confidence):
        try:
            conn = mysql.connector.connect(**self.db_cfg)
            cur  = conn.cursor()
            cur.execute(
                "INSERT INTO events (session_id, event_type, confidence) VALUES (%s, %s, %s)",
                (self.session_id, event_type, confidence)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"DB log error: {e}")

    def _update_risk_score(self, event_type):
        weight = self.RISK_WEIGHTS.get(event_type, 3)
        try:
            conn = mysql.connector.connect(**self.db_cfg)
            cur  = conn.cursor()
            cur.execute(
                "UPDATE sessions SET risk_score = risk_score + %s WHERE id = %s",
                (weight, self.session_id)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Risk score error: {e}")

    def _update_session_end(self):
        try:
            conn = mysql.connector.connect(**self.db_cfg)
            cur  = conn.cursor()
            cur.execute(
                "UPDATE sessions SET end_time = NOW() WHERE id = %s",
                (self.session_id,)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Session end error: {e}")

    def _send_alert_email(self, event_type, image_path, location):
        import smtplib, os
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.base import MIMEBase
        from email import encoders

        toaddr = getattr(self, 'driver_email', None)
        if not toaddr:
            print("Email skipped: no address")
            return

        fromaddr = "sudeshamegam79@gmail.com"

        msg = MIMEMultipart()
        msg['From'] = fromaddr
        msg['To'] = toaddr
        msg['Subject'] = f"Driver Alert: {event_type.upper()}"

        msg.attach(MIMEText(
            f"Alert: {event_type}\n"
            f"Driver: {self.username}\n"
            f"Location: {location}\n"
            f"Time: {datetime.now()}",
            'plain'
        ))

        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as f:
                p = MIMEBase('application', 'octet-stream')
                p.set_payload(f.read())
                encoders.encode_base64(p)
                p.add_header('Content-Disposition', f"attachment; filename={image_path}")
                msg.attach(p)

        try:
            s = smtplib.SMTP('smtp.gmail.com', 587)
            s.starttls()
            s.login(fromaddr, "ixcy hirl frzw zhgx")
            s.sendmail(fromaddr, toaddr, msg.as_string())
            s.quit()
            print("Email sent")
        except Exception as e:
            print("Email failed:", e)

# ── Routes ─────────────────────────────────────────────────────────────────────
@app.route("/")
def homepage():
    return render_template('index.html')


@app.route("/AdminLogin")
def AdminLogin():
    return render_template('AdminLogin.html')


@app.route("/DriverLogin")
def DriverLogin():
    return render_template('DriverLogin.html')


@app.route("/AdminHome")
def AdminHome():
    conn = mysql.connector.connect(**DB_CFG)
    cur  = conn.cursor()
    cur.execute("SELECT * FROM regtb")
    data = cur.fetchall()
    conn.close()
    return render_template('AdminHome.html', data=data)


@app.route("/NewOwner")
def NewOwner():
    return render_template('NewOwner.html')


@app.route("/OwnerInfo")
def OwnerInfo():
    conn = mysql.connector.connect(**DB_CFG)
    cur  = conn.cursor()
    cur.execute("SELECT * FROM ownertb")
    data = cur.fetchall()
    conn.close()
    return render_template('OwnerInfo.html', data=data)


@app.route("/NewDriver")
def NewDriver():
    import LiveRecognition as liv
    del sys.modules["LiveRecognition"]

    conn = mysql.connector.connect(**DB_CFG)
    cur  = conn.cursor()
    cur.execute("SELECT * FROM ownertb")
    data = cur.fetchall()
    conn.close()
    return render_template('NewDriver.html', company=data)


@app.route("/adminlogin", methods=['GET', 'POST'])
def adminlogin():
    if request.method == 'POST':
        if request.form['uname'] == 'admin' or request.form['password'] == 'admin':
            conn = mysql.connector.connect(**DB_CFG)
            cur  = conn.cursor()
            cur.execute("SELECT * FROM regtb")
            data = cur.fetchall()
            conn.close()
            return render_template('AdminHome.html', data=data)
        else:
            return render_template('index.html')


@app.route("/newdriver", methods=['GET', 'POST'])
def newdriver():
    if request.method == 'POST':
        uname    = request.form['uname']
        company  = request.form['company']
        dno      = request.form['dno']
        ano      = request.form['ano']
        exp      = request.form['exp']
        password = request.form['password']

        conn   = mysql.connector.connect(**DB_CFG)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ownertb WHERE CompanyName=%s", (company,))
        data   = cursor.fetchone()
        conn.close()

        if not data:
            return 'Company not found!'

        Mobile  = data[3]
        Email   = data[4]
        Address = data[5]

        conn   = mysql.connector.connect(**DB_CFG)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO regtb(CompanyName,Mobile,EmailId,Address,Licence,Aadhar,Experience,UserName,Password) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (company, Mobile, Email, Address, dno, ano, exp, uname, password)
        )
        conn.commit()
        conn.close()

    return render_template("DriverLogin.html")


@app.route("/newowner", methods=['GET', 'POST'])
def newowner():
    if request.method == 'POST':
        oname   = request.form['oname']
        cname   = request.form['cname']
        mobile  = request.form['mobile']
        email   = request.form['email']
        address = request.form['address']

        conn   = mysql.connector.connect(**DB_CFG)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO ownertb(OwnerName,CompanyName,mobile,email,address) VALUES (%s,%s,%s,%s,%s)",
            (oname, cname, mobile, email, address)
        )
        conn.commit()
        conn.close()

    conn = mysql.connector.connect(**DB_CFG)
    cur  = conn.cursor()
    cur.execute("SELECT * FROM ownertb")
    data = cur.fetchall()
    conn.close()
    return render_template('OwnerInfo.html', data=data)


@app.route("/driverlogin", methods=['GET', 'POST'])
def userlogin():
    if request.method == 'POST':
        username = request.form['uname']
        password = request.form['password']
        session['dname'] = username

        # Clear face check table for this session
        conn   = mysql.connector.connect(**DB_CFG)
        cursor = conn.cursor()
        cursor.execute("TRUNCATE TABLE checktb")
        conn.commit()
        conn.close()

        # Validate credentials
        conn   = mysql.connector.connect(**DB_CFG)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM regtb WHERE UserName=%s AND Password=%s",
            (username, password)
        )
        data = cursor.fetchone()
        conn.close()

        if data is None:
            return 'Username or Password is wrong'

        session['mob']   = data[2]
        session['email'] = data[3]

        # Run face recognition
        import LiveRecognition1 as liv
        del sys.modules["LiveRecognition1"]

        return check()

def check():
    username = session['dname']

    # Verify face match
    conn   = mysql.connector.connect(**DB_CFG)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM checktb WHERE UserName=%s", (username,))
    data   = cursor.fetchone()
    conn.close()

    if data is None:
       return 'Face Mismatch'

    # Create a new session row in DB
    conn = mysql.connector.connect(**DB_CFG)
    cur  = conn.cursor()
    cur.execute("INSERT INTO sessions (username) VALUES (%s)", (username,))
    conn.commit()
    session_id = cur.lastrowid
    conn.close()

    # Start background detection engine
    engine = DetectionEngine(session_id, username, socketio, DB_CFG)
    engine.driver_email = session['email']
    active_engines[username] = engine
    engine.start()

    return render_template('DriverHome.html')





@app.route("/stop_session", methods=['POST'])
def stop_session():
    username = session.get('dname')
    engine   = active_engines.pop(username, None)
    if engine:
        engine.stop()
    return jsonify({'status': 'stopped'})


# ── Analytics API ──────────────────────────────────────────────────────────────
@app.route("/api/sessions")
def api_sessions():
    username = session.get('dname')
    conn = mysql.connector.connect(**DB_CFG)
    cur  = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT id, start_time, end_time, risk_score FROM sessions "
        "WHERE username=%s ORDER BY start_time DESC LIMIT 30",
        (username,)
    )
    data = cur.fetchall()
    conn.close()
    # Convert datetime objects to strings for JSON
    for row in data:
        if row['start_time']:
            row['start_time'] = str(row['start_time'])
        if row['end_time']:
            row['end_time'] = str(row['end_time'])
    return jsonify(data)


@app.route("/api/sessions/<int:sid>/events")
def api_session_events(sid):
    conn = mysql.connector.connect(**DB_CFG)
    cur  = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT event_type, confidence, timestamp FROM events "
        "WHERE session_id=%s ORDER BY timestamp",
        (sid,)
    )
    data = cur.fetchall()
    conn.close()
    for row in data:
        if row['timestamp']:
            row['timestamp'] = str(row['timestamp'])
    return jsonify(data)


@app.route("/api/analytics/summary")
def api_summary():
    username = session.get('dname')
    conn = mysql.connector.connect(**DB_CFG)
    cur  = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT
            e.event_type,
            COUNT(e.id)      AS type_count,
            AVG(e.confidence) AS avg_confidence
        FROM sessions s
        LEFT JOIN events e ON e.session_id = s.id
        WHERE s.username = %s AND e.event_type IS NOT NULL
        GROUP BY e.event_type
    """, (username,))
    data = cur.fetchall()
    conn.close()
    return jsonify(data)


@app.route("/api/risk_history")
def api_risk_history():
    username = session.get('dname')
    conn = mysql.connector.connect(**DB_CFG)
    cur  = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT id, risk_score, start_time FROM sessions "
        "WHERE username=%s ORDER BY start_time ASC LIMIT 20",
        (username,)
    )
    data = cur.fetchall()
    conn.close()
    for row in data:
        if row['start_time']:
            row['start_time'] = str(row['start_time'])
    return jsonify(data)


@app.route('/update_location', methods=['POST'])
def update_location():
    data = request.get_json()

    print("LOCATION RECEIVED:", data)

    username = session.get('dname')
    engine = active_engines.get(username)

    if engine and data:
        # 👇 THIS IS WHERE YOUR LINE GOES
        engine.location = f"{data['lat']}, {data['lon']}"

    return jsonify({'status': 'ok'})




# ── Helpers ────────────────────────────────────────────────────────────────────
def examvales1():
    return session['dname'], session['email'], session['mob']



#def sendmail():
    #_send_alert_email(self, event_type, image_path, location)


def emotion():
    # Legacy YOLOv3-tiny distraction detection — kept for reference
    # This is now handled by DetectionEngine._inference_loop()
    pass


def sendmsg(targetno, message):
    import requests
    requests.post(
        "http://sms.creativepoint.in/api/push.json?apikey=6555c521622c1&route=transsms&sender=FSSMSS&mobileno=" + targetno + "&text=Dear customer your msg is " + message + "  Sent By FSMSG FSSMSS")

if __name__ == '__main__':
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True)


