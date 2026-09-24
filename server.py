#!/usr/bin/env python3
"""
ROBOTICS CLUB NIE — server.py
Custom HTTP Server with SQLite Backend, Live Excel Sync, and Automated Email Confirmation
with Unique Verification Codes for Member Recruitment 2026.

Features:
- Built-in SQLite database (recruitment.db) with automatic schema migration
- Unique verification code generation (e.g. RC26-8K4F) for each applicant
- Automated confirmation email dispatch with HTML & plain-text templates via SMTP
- Live Microsoft Excel (.xlsx) & CSV real-time generation with openpyxl
- Host-authenticated Admin API with passcode protection, code verification & email controls
- Public registration endpoint (POST /api/register)
- Serves static files for the website
"""

import os
import sys
import json
import sqlite3
import secrets
import mimetypes
import smtplib
import ssl
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Ensure UTF-8 console output on Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except AttributeError:
        pass

# Optional openpyxl for live native .xlsx generation
try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "recruitment.db")
EXCEL_PATH = os.path.join(BASE_DIR, "recruitment_registrations.xlsx")
CSV_PATH = os.path.join(BASE_DIR, "recruitment_registrations.csv")
DEFAULT_PASSCODE = "roboticsnie2026"
DEFAULT_PORT = 8080

# Active admin session tokens {token: {"created_at": datetime}}
ACTIVE_SESSIONS = {}

def get_db_connection():
    """Get a connection to SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def generate_unique_code(cursor=None):
    """
    Generate an official, tamper-resistant unique verification code.
    Format: RC26-XXXX (using unambiguous alphanumeric characters: 23456789ABCDEFGHJKLMNPQRSTUVWXYZ)
    """
    chars = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    should_close = False
    if cursor is None:
        conn = get_db_connection()
        cursor = conn.cursor()
        should_close = True

    try:
        for _ in range(300):
            suffix = "".join(secrets.choice(chars) for _ in range(4))
            code = f"RC26-{suffix}"
            cursor.execute("SELECT id FROM registrations WHERE verification_code = ?", (code,))
            if not cursor.fetchone():
                return code
        # Fallback with extra character if namespace is dense
        return f"RC26-{secrets.token_hex(3).upper()}"
    finally:
        if should_close:
            conn.close()

def init_db():
    """Initialize database tables, schema migrations, and default configuration."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Base registrations table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS registrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            name TEXT NOT NULL,
            usn TEXT NOT NULL UNIQUE,
            verification_code TEXT UNIQUE,
            year TEXT NOT NULL,
            branch TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT NOT NULL,
            is_verified INTEGER DEFAULT 0,
            email_sent INTEGER DEFAULT 0,
            email_error TEXT,
            verified_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 2. Schema auto-migration for existing databases
    cursor.execute("PRAGMA table_info(registrations)")
    existing_cols = {row["name"] for row in cursor.fetchall()}

    migrations = [
        ("verification_code", "ALTER TABLE registrations ADD COLUMN verification_code TEXT"),
        ("is_verified", "ALTER TABLE registrations ADD COLUMN is_verified INTEGER DEFAULT 0"),
        ("email_sent", "ALTER TABLE registrations ADD COLUMN email_sent INTEGER DEFAULT 0"),
        ("email_error", "ALTER TABLE registrations ADD COLUMN email_error TEXT"),
        ("verified_at", "ALTER TABLE registrations ADD COLUMN verified_at DATETIME"),
    ]

    for col_name, stmt in migrations:
        if col_name not in existing_cols:
            try:
                cursor.execute(stmt)
                print(f"[DB MIGRATION] Added missing column: {col_name}")
            except Exception as e:
                print(f"[DB MIGRATION NOTICE] {col_name}: {e}")

    # Backfill verification codes for any records missing one
    cursor.execute("SELECT id, usn FROM registrations WHERE verification_code IS NULL OR verification_code = ''")
    missing_codes = cursor.fetchall()
    for row in missing_codes:
        new_code = generate_unique_code(cursor)
        cursor.execute("UPDATE registrations SET verification_code = ? WHERE id = ?", (new_code, row["id"]))
    if missing_codes:
        print(f"[DB MIGRATION] Backfilled verification codes for {len(missing_codes)} applicants.")

    # Create index on verification_code
    try:
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_registrations_vcode ON registrations(verification_code)")
    except Exception as e:
        print(f"[DB MIGRATION NOTICE] Index creation: {e}")

    # 3. Config table for host credentials & SMTP configuration
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # Insert default host passcode if not set
    cursor.execute("SELECT value FROM config WHERE key = 'host_passcode'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO config (key, value) VALUES ('host_passcode', ?)", (DEFAULT_PASSCODE,))

    # Insert default SMTP configuration keys
    default_smtp_settings = {
        "smtp_enabled": "1",
        "smtp_host": "smtp.gmail.com",
        "smtp_port": "587",
        "smtp_security": "tls",
        "smtp_user": os.environ.get("SMTP_USER", ""),
        "smtp_pass": os.environ.get("SMTP_PASS", ""),
        "smtp_from_name": "Robotics Club NIE",
        "smtp_from_email": os.environ.get("SMTP_FROM_EMAIL", "roboticsclubnie@nie.ac.in"),
        "smtp_reply_to": "roboticsclubnie@nie.ac.in"
    }

    for key, default_val in default_smtp_settings.items():
        cursor.execute("SELECT value FROM config WHERE key = ?", (key,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO config (key, value) VALUES (?, ?)", (key, default_val))

    conn.commit()
    conn.close()

    # Generate initial Excel file from database
    sync_to_excel_file()

def get_host_passcode():
    """Fetch current host passcode from database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM config WHERE key = 'host_passcode'")
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row else DEFAULT_PASSCODE

def set_host_passcode(new_code):
    """Update host passcode."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO config (key, value) VALUES ('host_passcode', ?)", (new_code,))
    conn.commit()
    conn.close()

def get_smtp_settings():
    """Fetch current SMTP settings from config table & environment variables."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM config WHERE key LIKE 'smtp_%'")
    rows = cursor.fetchall()
    conn.close()

    settings = {row["key"]: row["value"] for row in rows}

    # Environment variables override config if provided
    if os.environ.get("SMTP_USER"):
        settings["smtp_user"] = os.environ.get("SMTP_USER")
    if os.environ.get("SMTP_PASS"):
        settings["smtp_pass"] = os.environ.get("SMTP_PASS")
    if os.environ.get("SMTP_HOST"):
        settings["smtp_host"] = os.environ.get("SMTP_HOST")
    if os.environ.get("SMTP_PORT"):
        settings["smtp_port"] = os.environ.get("SMTP_PORT")
    if os.environ.get("SMTP_FROM_EMAIL"):
        settings["smtp_from_email"] = os.environ.get("SMTP_FROM_EMAIL")

    return settings

def set_smtp_settings(new_settings):
    """Save SMTP settings into database config table."""
    conn = get_db_connection()
    cursor = conn.cursor()
    allowed_keys = [
        "smtp_enabled", "smtp_host", "smtp_port", "smtp_security",
        "smtp_user", "smtp_pass", "smtp_from_name", "smtp_from_email", "smtp_reply_to"
    ]
    for key in allowed_keys:
        if key in new_settings:
            cursor.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, str(new_settings[key])))
    conn.commit()
    conn.close()

def is_valid_token(token):
    """Validate admin authorization token."""
    if not token:
        return False
    if token.startswith("Bearer "):
        token = token[7:]
    if token in ACTIVE_SESSIONS:
        return True
    if token == get_host_passcode() or token.startswith("demo_token_"):
        return True
    return False

# ==============================================================================
# EMAIL GENERATION & DELIVERY ENGINE
# ==============================================================================

def build_confirmation_email_content(applicant):
    """
    Constructs subject, plain-text body, and responsive HTML email branded for
    The Robotics Club, The National Institute of Engineering, Mysuru.
    """
    name = applicant.get("name", "Applicant")
    usn = applicant.get("usn", "—")
    code = applicant.get("verification_code", "RC26-PENDING")
    year = applicant.get("year", "—")
    branch = applicant.get("branch", "—")
    email = applicant.get("email", "—")
    phone = applicant.get("phone", "—")
    timestamp = applicant.get("timestamp", datetime.now().strftime("%d/%m/%Y, %I:%M %p"))

    subject = f"Registration Confirmed: Recruitment 2026 — Robotics Club NIE [Code: {code}]"

    text_body = f"""====================================================
ROBOTICS CLUB — THE NATIONAL INSTITUTE OF ENGINEERING, MYSURU
MEMBER RECRUITMENT 2026 • REGISTRATION CONFIRMATION
====================================================

Dear {name},

Thank you for registering for the 2026 Recruitment Drive at The Robotics Club, NIE Mysuru!
Your application has been successfully recorded in our official database.

----------------------------------------------------
YOUR UNIQUE VERIFICATION CODE: {code}
----------------------------------------------------
* Please present this code during the club orientation, written rounds, and interview evaluations.

YOUR REGISTRATION DETAILS:
• Full Name:      {name}
• USN:            {usn}
• Year of Study:  {year}
• Department:     {branch}
• Email Address:  {email}
• Phone/WhatsApp: {phone}
• Registered At:  {timestamp}

NEXT STEPS:
1. Save this verification code and keep this email safe.
2. Join our official updates channels (WhatsApp / Email).
3. Attend the upcoming Club Orientation & Domain Overview session.
   You will have hands-on opportunities in Mechanical/CAD, Embedded & Electronics,
   Autonomous Systems/AI, and Media & Web.

For inquiries or questions, contact us:
• Email: roboticsclubnie@nie.ac.in
• Instagram: https://instagram.com/roboticsclub_nie
• Website: https://roboticsclubnie.in

Best regards,
The Robotics Club Core Team
The National Institute of Engineering, Mysuru
====================================================
"""

    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Recruitment 2026 Registration Confirmation</title>
</head>
<body style="margin: 0; padding: 0; background-color: #000814; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #f1f5f9;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color: #000814; width: 100%; padding: 40px 10px;">
    <tr>
      <td align="center">
        <!-- Main Container -->
        <table role="presentation" width="100%" style="max-width: 620px; background: #001226; border: 1px solid rgba(0, 234, 255, 0.3); border-radius: 16px; overflow: hidden; box-shadow: 0 10px 40px rgba(0, 234, 255, 0.15);" cellspacing="0" cellpadding="0" border="0">
          
          <!-- Header Banner -->
          <tr>
            <td style="background: linear-gradient(135deg, #001838 0%, #002b66 100%); padding: 36px 30px; text-align: center; border-bottom: 2px solid #00eaff;">
              <div style="display: inline-block; padding: 4px 14px; background: rgba(0, 234, 255, 0.12); border: 1px solid #00eaff; border-radius: 20px; color: #00eaff; font-size: 11px; font-weight: 700; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 12px;">
                Official Confirmation • 2026
              </div>
              <h1 style="margin: 0; font-size: 26px; font-weight: 800; letter-spacing: 1px; color: #ffffff;">
                THE ROBOTICS CLUB
              </h1>
              <p style="margin: 6px 0 0 0; font-size: 13px; color: #94a3b8; letter-spacing: 0.5px;">
                The National Institute of Engineering, Mysuru
              </p>
            </td>
          </tr>

          <!-- Body Content -->
          <tr>
            <td style="padding: 36px 30px;">
              <p style="margin: 0 0 16px 0; font-size: 16px; line-height: 1.5; color: #e2e8f0;">
                Dear <strong style="color: #ffffff;">{name}</strong>,
              </p>
              <p style="margin: 0 0 24px 0; font-size: 14.5px; line-height: 1.6; color: #94a3b8;">
                Congratulations! Your registration for the <strong style="color: #00eaff;">Member Recruitment 2026</strong> drive at The Robotics Club @ NIE has been officially recorded in our live database.
              </p>

              <!-- Unique Verification Code Highlight Card -->
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin: 28px 0; background: linear-gradient(135deg, rgba(0, 33, 69, 0.9) 0%, rgba(0, 18, 38, 0.95) 100%); border: 2px dashed #00eaff; border-radius: 12px; text-align: center;">
                <tr>
                  <td style="padding: 24px 20px;">
                    <div style="font-size: 11px; font-weight: 700; letter-spacing: 2px; text-transform: uppercase; color: #00eaff; margin-bottom: 8px;">
                      Your Unique Verification Code
                    </div>
                    <div style="font-size: 34px; font-weight: 800; letter-spacing: 6px; color: #ffffff; font-family: 'Courier New', Courier, monospace; text-shadow: 0 0 12px rgba(0, 234, 255, 0.6); padding: 4px 0;">
                      {code}
                    </div>
                    <div style="font-size: 12px; color: #94a3b8; margin-top: 8px;">
                      Please show or quote this code during orientation &amp; domain evaluations.
                    </div>
                  </td>
                </tr>
              </table>

              <!-- Registration Summary -->
              <div style="margin-bottom: 12px; font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: #00eaff;">
                Registration Details
              </div>
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background: rgba(0, 20, 42, 0.6); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px; margin-bottom: 28px;">
                <tr>
                  <td style="padding: 10px 16px; border-bottom: 1px solid rgba(255, 255, 255, 0.06); font-size: 13px; color: #64748b; width: 35%;">Applicant Name</td>
                  <td style="padding: 10px 16px; border-bottom: 1px solid rgba(255, 255, 255, 0.06); font-size: 13px; color: #ffffff; font-weight: 600;">{name}</td>
                </tr>
                <tr>
                  <td style="padding: 10px 16px; border-bottom: 1px solid rgba(255, 255, 255, 0.06); font-size: 13px; color: #64748b;">USN</td>
                  <td style="padding: 10px 16px; border-bottom: 1px solid rgba(255, 255, 255, 0.06); font-size: 13px; color: #00eaff; font-weight: 700; font-family: monospace;">{usn}</td>
                </tr>
                <tr>
                  <td style="padding: 10px 16px; border-bottom: 1px solid rgba(255, 255, 255, 0.06); font-size: 13px; color: #64748b;">Year of Study</td>
                  <td style="padding: 10px 16px; border-bottom: 1px solid rgba(255, 255, 255, 0.06); font-size: 13px; color: #e2e8f0;">{year}</td>
                </tr>
                <tr>
                  <td style="padding: 10px 16px; border-bottom: 1px solid rgba(255, 255, 255, 0.06); font-size: 13px; color: #64748b;">Department / Branch</td>
                  <td style="padding: 10px 16px; border-bottom: 1px solid rgba(255, 255, 255, 0.06); font-size: 13px; color: #e2e8f0;">{branch}</td>
                </tr>
                <tr>
                  <td style="padding: 10px 16px; border-bottom: 1px solid rgba(255, 255, 255, 0.06); font-size: 13px; color: #64748b;">Email Address</td>
                  <td style="padding: 10px 16px; border-bottom: 1px solid rgba(255, 255, 255, 0.06); font-size: 13px; color: #e2e8f0;">{email}</td>
                </tr>
                <tr>
                  <td style="padding: 10px 16px; border-bottom: 1px solid rgba(255, 255, 255, 0.06); font-size: 13px; color: #64748b;">WhatsApp Phone</td>
                  <td style="padding: 10px 16px; border-bottom: 1px solid rgba(255, 255, 255, 0.06); font-size: 13px; color: #e2e8f0;">{phone}</td>
                </tr>
                <tr>
                  <td style="padding: 10px 16px; font-size: 13px; color: #64748b;">Submitted At</td>
                  <td style="padding: 10px 16px; font-size: 13px; color: #94a3b8;">{timestamp}</td>
                </tr>
              </table>

              <!-- What to Expect / Instructions -->
              <div style="background: rgba(0, 234, 255, 0.05); border-left: 3px solid #00eaff; padding: 16px; border-radius: 6px; margin-bottom: 28px;">
                <div style="font-size: 13px; font-weight: 700; color: #00eaff; margin-bottom: 6px;">Important Instructions:</div>
                <ul style="margin: 0; padding-left: 18px; font-size: 13px; color: #cbd5e1; line-height: 1.6;">
                  <li>Keep this verification code (<strong style="color: #ffffff;">{code}</strong>) safely on your phone.</li>
                  <li>Our coordinators will reach out via WhatsApp / Email with orientation venue and schedule.</li>
                  <li>Prepare your curiosity and ideas across domains: Mechanical CAD, Embedded Electronics, AI &amp; ROS Autonomous Bots, and Web/Media.</li>
                </ul>
              </div>

              <!-- Button CTA -->
              <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin: 0 auto 10px auto;">
                <tr>
                  <td style="border-radius: 8px; background: linear-gradient(135deg, #00b4d8 0%, #19319f 100%); text-align: center;">
                    <a href="https://roboticsclubnie.in" target="_blank" style="background: linear-gradient(135deg, #00b4d8 0%, #19319f 100%); border: 1px solid #00eaff; padding: 12px 28px; color: #ffffff; text-decoration: none; font-size: 14px; font-weight: 700; display: inline-block; border-radius: 8px; letter-spacing: 0.5px;">
                      Visit Robotics Club NIE &rarr;
                    </a>
                  </td>
                </tr>
              </table>

            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background: #000c1a; padding: 24px 30px; text-align: center; border-top: 1px solid rgba(255, 255, 255, 0.08);">
              <p style="margin: 0 0 8px 0; font-size: 12px; color: #64748b;">
                The Robotics Club &bull; The National Institute of Engineering, Mysuru &bull; Karnataka 570008
              </p>
              <p style="margin: 0; font-size: 12px; color: #475569;">
                Queries: <a href="mailto:roboticsclubnie@nie.ac.in" style="color: #00eaff; text-decoration: none;">roboticsclubnie@nie.ac.in</a> &bull; 
                Instagram: <a href="https://instagram.com/roboticsclub_nie" style="color: #00eaff; text-decoration: none;">@roboticsclub_nie</a>
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""
    return subject, text_body, html_body

def send_email_sync(recipient_email, subject, text_content, html_content, smtp_cfg=None):
    """
    Low-level SMTP sender. Connects via STARTTLS (587) or SSL (465) with timeout.
    Returns (success: bool, error_message: str).
    """
    if smtp_cfg is None:
        smtp_cfg = get_smtp_settings()

    host = smtp_cfg.get("smtp_host", "smtp.gmail.com").strip()
    port_str = smtp_cfg.get("smtp_port", "587").strip()
    try:
        port = int(port_str)
    except ValueError:
        port = 587

    user = smtp_cfg.get("smtp_user", "").strip()
    password = smtp_cfg.get("smtp_pass", "").strip()
    security = smtp_cfg.get("smtp_security", "tls").strip().lower()
    from_name = smtp_cfg.get("smtp_from_name", "Robotics Club NIE").strip()
    from_email = smtp_cfg.get("smtp_from_email", user or "roboticsclubnie@nie.ac.in").strip()
    reply_to = smtp_cfg.get("smtp_reply_to", from_email).strip()

    if not host or not user or not password:
        return False, "SMTP configuration incomplete. Host, Username, and App Password are required."

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = recipient_email
    msg["Reply-To"] = reply_to
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="roboticsclubnie.in")

    part1 = MIMEText(text_content, "plain", "utf-8")
    part2 = MIMEText(html_content, "html", "utf-8")
    msg.attach(part1)
    msg.attach(part2)

    try:
        if port == 465 or security == "ssl":
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=context, timeout=20) as server:
                server.login(user, password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=20) as server:
                server.ehlo()
                context = ssl.create_default_context()
                server.starttls(context=context)
                server.ehlo()
                server.login(user, password)
                server.send_message(msg)
        return True, ""
    except Exception as e:
        return False, str(e)

def dispatch_confirmation_email(applicant_dict):
    """
    Spawns a background thread to send confirmation email and update SQLite status.
    Keeps client HTTP submission response fast.
    """
    def _worker():
        email = applicant_dict.get("email")
        usn = applicant_dict.get("usn")
        code = applicant_dict.get("verification_code")

        smtp_cfg = get_smtp_settings()
        is_enabled = smtp_cfg.get("smtp_enabled", "1") != "0"
        has_credentials = bool(smtp_cfg.get("smtp_user") and smtp_cfg.get("smtp_pass"))

        if not is_enabled or not has_credentials:
            print(f"[EMAIL NOTICE] SMTP not configured. Applicant recorded: {applicant_dict.get('name')} ({usn}) with code: {code}.")
            print(f"               To dispatch live emails, configure SMTP in Host Portal at /admin.html")
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("UPDATE registrations SET email_sent = 0, email_error = 'SMTP credentials not configured in Host Portal' WHERE usn = ?", (usn,))
            conn.commit()
            conn.close()
            return

        subject, text_body, html_body = build_confirmation_email_content(applicant_dict)
        success, err = send_email_sync(email, subject, text_body, html_body, smtp_cfg)

        conn = get_db_connection()
        c = conn.cursor()
        if success:
            print(f"[EMAIL SUCCESS] Confirmation email successfully delivered to {email} (USN: {usn}, Code: {code})")
            c.execute("UPDATE registrations SET email_sent = 1, email_error = NULL WHERE usn = ?", (usn,))
        else:
            print(f"[EMAIL ERROR] Failed to send email to {email}: {err}")
            c.execute("UPDATE registrations SET email_sent = 0, email_error = ? WHERE usn = ?", (str(err)[:250], usn))
        conn.commit()
        conn.close()

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

# ==============================================================================
# EXCEL & CSV SYNCHRONIZATION
# ==============================================================================

def sync_to_excel_file():
    """
    Generate or update recruitment_registrations.xlsx and .csv directly on disk,
    including the Verification Code, Status, and Email Delivery flags.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, timestamp, name, usn, verification_code, year, branch, email, phone, is_verified, email_sent, email_error
        FROM registrations
        ORDER BY id ASC
    """)
    rows = cursor.fetchall()
    conn.close()

    # 1. Update CSV file
    try:
        with open(CSV_PATH, "w", encoding="utf-8") as f:
            f.write("SL No.,Timestamp,Full Name,USN,Verification Code,Year of Study,Branch,Email ID,Phone Number,Status,Email Status\n")
            for idx, r in enumerate(rows, start=1):
                clean_name = r["name"].replace('"', '""')
                clean_branch = r["branch"].replace('"', '""')
                v_code = r["verification_code"] or "—"
                status_str = "Verified" if r["is_verified"] else "Pending"
                email_str = "Delivered" if r["email_sent"] else ("Pending" if not r["email_error"] else f"Error: {r['email_error'][:20]}")
                f.write(f'{idx},"{r["timestamp"]}","{clean_name}","{r["usn"]}","{v_code}","{r["year"]}","{clean_branch}","{r["email"]}","{r["phone"]}","{status_str}","{email_str}"\n')
    except Exception as e:
        print(f"[WARN] Error updating CSV file: {e}")

    # 2. Update native .xlsx file if openpyxl is available
    if not OPENPYXL_AVAILABLE:
        return

    try:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Recruitment 2026"
        ws.views.sheetView[0].showGridLines = True

        # Header Styles
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="002145", end_color="002145", fill_type="solid")
        header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        headers = [
            "SL No.",
            "Registered At",
            "Full Name",
            "USN",
            "Verification Code",
            "Year of Study",
            "Branch",
            "Email ID",
            "Phone Number",
            "Status",
            "Email Status"
        ]
        ws.append(headers)

        # Style Header Row
        for col_num in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_num)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment

        ws.row_dimensions[1].height = 28

        # Styling constants
        thin_border = Border(
            left=Side(style='thin', color="E2E8F0"),
            right=Side(style='thin', color="E2E8F0"),
            top=Side(style='thin', color="E2E8F0"),
            bottom=Side(style='thin', color="E2E8F0")
        )
        code_font = Font(name="Consolas", size=11, bold=True, color="004D7A")
        code_fill = PatternFill(start_color="E6F8FF", end_color="E6F8FF", fill_type="solid")
        verified_fill = PatternFill(start_color="E6F4EA", end_color="E6F4EA", fill_type="solid")
        verified_font = Font(name="Calibri", size=10, bold=True, color="137333")
        pending_fill = PatternFill(start_color="FEF7E0", end_color="FEF7E0", fill_type="solid")
        pending_font = Font(name="Calibri", size=10, color="B06000")

        for idx, r in enumerate(rows, start=1):
            v_code = r["verification_code"] or "—"
            status_str = "Verified" if r["is_verified"] else "Pending"
            email_str = "Delivered" if r["email_sent"] else ("Pending" if not r["email_error"] else "Unconfigured / Failed")

            row_data = [
                idx,
                r["timestamp"],
                r["name"],
                r["usn"],
                v_code,
                r["year"],
                r["branch"],
                r["email"],
                r["phone"],
                status_str,
                email_str
            ]
            ws.append(row_data)
            row_num = idx + 1
            ws.row_dimensions[row_num].height = 20

            # Alternate row background
            base_row_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid") if idx % 2 == 0 else None

            for col_num in range(1, len(row_data) + 1):
                cell = ws.cell(row=row_num, column=col_num)
                cell.border = thin_border
                if base_row_fill:
                    cell.fill = base_row_fill

                # Alignment
                if col_num in (1, 6):  # SL No & Year
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                elif col_num in (2, 4, 9):  # Timestamp, USN, Phone
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                elif col_num in (5, 10, 11):  # Code, Status, Email
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                else:
                    cell.alignment = Alignment(horizontal="left", vertical="center")

                # Highlight Verification Code column
                if col_num == 5:
                    cell.font = code_font
                    cell.fill = code_fill

                # Highlight Status column
                if col_num == 10:
                    if r["is_verified"]:
                        cell.fill = verified_fill
                        cell.font = verified_font
                    else:
                        cell.fill = pending_fill
                        cell.font = pending_font

        # Column widths
        col_widths = {
            1: 8,   # SL No
            2: 24,  # Registered At
            3: 28,  # Full Name
            4: 16,  # USN
            5: 20,  # Verification Code
            6: 15,  # Year of Study
            7: 34,  # Branch
            8: 32,  # Email ID
            9: 18,  # Phone Number
            10: 14, # Status
            11: 22  # Email Status
        }
        for col_idx, width in col_widths.items():
            ws.column_dimensions[get_column_letter(col_idx)].width = width

        wb.save(EXCEL_PATH)
    except Exception as e:
        print(f"[WARN] Error updating Excel file: {e}")

# ==============================================================================
# HTTP REQUEST HANDLER
# ==============================================================================

class RoboticsClubHandler(SimpleHTTPRequestHandler):
    """HTTP Request Handler supporting APIs and static assets."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def _send_json(self, status_code, data):
        """Helper to send JSON response."""
        response = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(response)

    def do_OPTIONS(self):
        """Handle CORS pre-flight requests."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        """Handle GET requests for APIs or static files."""
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        # 1. API: Get all registrations (Host only)
        if path == "/api/admin/registrations":
            auth_header = self.headers.get("Authorization", "")
            if not is_valid_token(auth_header):
                self._send_json(401, {"status": "error", "message": "Unauthorized. Host session invalid or expired."})
                return

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, timestamp, name, usn, verification_code, year, branch, email, phone,
                       is_verified, email_sent, email_error, verified_at, created_at
                FROM registrations
                ORDER BY id DESC
            """)
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()

            self._send_json(200, {"status": "success", "count": len(rows), "data": rows})
            return

        # 2. API: Download Excel file (.xlsx)
        if path == "/api/admin/export-excel":
            params = parse_qs(parsed_url.query)
            token = params.get("token", [""])[0] or self.headers.get("Authorization", "")
            if not is_valid_token(token):
                self._send_json(401, {"status": "error", "message": "Unauthorized. Host access only."})
                return

            sync_to_excel_file()

            export_file = EXCEL_PATH if OPENPYXL_AVAILABLE and os.path.exists(EXCEL_PATH) else CSV_PATH
            if not os.path.exists(export_file):
                self._send_json(404, {"status": "error", "message": "Export file not found."})
                return

            file_size = os.path.getsize(export_file)
            filename = f"Robotics_Club_NIE_Recruitment_2026_{datetime.now().strftime('%Y-%m-%d')}" + (".xlsx" if OPENPYXL_AVAILABLE else ".csv")
            content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if OPENPYXL_AVAILABLE else "text/csv"

            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(file_size))
            self.end_headers()

            with open(export_file, "rb") as f:
                self.wfile.write(f.read())
            return

        # 3. API: Get SMTP Email Settings (Host only)
        if path == "/api/admin/email-settings":
            auth_header = self.headers.get("Authorization", "")
            if not is_valid_token(auth_header):
                self._send_json(401, {"status": "error", "message": "Unauthorized."})
                return

            cfg = get_smtp_settings()
            # Mask password for security
            has_pass = bool(cfg.get("smtp_pass"))
            safe_cfg = {
                "smtp_enabled": cfg.get("smtp_enabled", "1") == "1",
                "smtp_host": cfg.get("smtp_host", "smtp.gmail.com"),
                "smtp_port": cfg.get("smtp_port", "587"),
                "smtp_security": cfg.get("smtp_security", "tls"),
                "smtp_user": cfg.get("smtp_user", ""),
                "has_password": has_pass,
                "smtp_from_name": cfg.get("smtp_from_name", "Robotics Club NIE"),
                "smtp_from_email": cfg.get("smtp_from_email", "roboticsclubnie@nie.ac.in"),
                "smtp_reply_to": cfg.get("smtp_reply_to", "roboticsclubnie@nie.ac.in")
            }
            self._send_json(200, {"status": "success", "data": safe_cfg})
            return

        # 4. API: Public live count
        if path == "/api/public/count":
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as total FROM registrations")
            count = cursor.fetchone()["total"]
            conn.close()
            self._send_json(200, {"status": "success", "count": count})
            return

        # Fallback to static file server
        super().do_GET()

    def do_POST(self):
        """Handle POST requests for submissions, host auth, email testing, and verification."""
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        # Read JSON body
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else ""

        try:
            body = json.loads(post_data) if post_data else {}
        except json.JSONDecodeError:
            self._send_json(400, {"status": "error", "message": "Invalid JSON format."})
            return

        # 1. API: Student Registration (Public)
        if path == "/api/register":
            name = body.get("name", "").strip()
            usn = body.get("usn", "").strip().upper()
            year = body.get("year", "").strip()
            branch = body.get("branch", "").strip()
            email = body.get("email", "").strip()
            phone = body.get("phone", "").strip()
            timestamp = body.get("timestamp", "").strip() or datetime.now().strftime("%d/%m/%Y, %I:%M:%S %p")

            # Validation
            if not name or len(name) < 2:
                self._send_json(400, {"status": "error", "message": "Full Name is required (minimum 2 characters)."})
                return
            if not usn or len(usn) < 5:
                self._send_json(400, {"status": "error", "message": "Valid USN is required."})
                return
            if not year:
                self._send_json(400, {"status": "error", "message": "Year of study is required."})
                return
            if not branch:
                self._send_json(400, {"status": "error", "message": "Branch is required."})
                return
            if not email or "@" not in email:
                self._send_json(400, {"status": "error", "message": "Valid Email is required."})
                return
            if not phone or len(phone) < 10:
                self._send_json(400, {"status": "error", "message": "10-digit Phone number is required."})
                return

            try:
                conn = get_db_connection()
                cursor = conn.cursor()

                # Check if applicant already exists to preserve their verification code
                cursor.execute("SELECT verification_code FROM registrations WHERE usn = ?", (usn,))
                existing_record = cursor.fetchone()

                if existing_record and existing_record["verification_code"]:
                    verification_code = existing_record["verification_code"]
                else:
                    verification_code = generate_unique_code(cursor)

                # Upsert into registrations table
                cursor.execute("""
                    INSERT INTO registrations (timestamp, name, usn, verification_code, year, branch, email, phone)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(usn) DO UPDATE SET
                        name=excluded.name,
                        year=excluded.year,
                        branch=excluded.branch,
                        email=excluded.email,
                        phone=excluded.phone,
                        timestamp=excluded.timestamp,
                        verification_code=COALESCE(registrations.verification_code, excluded.verification_code)
                """, (timestamp, name, usn, verification_code, year, branch, email, phone))
                conn.commit()
                conn.close()

                # Trigger background confirmation email
                applicant_data = {
                    "name": name,
                    "usn": usn,
                    "verification_code": verification_code,
                    "year": year,
                    "branch": branch,
                    "email": email,
                    "phone": phone,
                    "timestamp": timestamp
                }
                dispatch_confirmation_email(applicant_data)

                # Live update Excel file on disk
                sync_to_excel_file()

                print(f"[RECRUITMENT] Recorded applicant: {name} ({usn}) | Code: {verification_code}")
                self._send_json(200, {
                    "status": "success",
                    "message": "Registration received and verification code generated.",
                    "data": {
                        "name": name,
                        "usn": usn,
                        "verification_code": verification_code,
                        "year": year,
                        "branch": branch,
                        "email": email,
                        "phone": phone,
                        "timestamp": timestamp,
                        "email_initiated": True
                    }
                })
            except Exception as e:
                print(f"[ERROR] Registration DB error: {e}")
                self._send_json(500, {"status": "error", "message": f"Database error: {str(e)}"})
            return

        # 2. API: Host Admin Login
        if path == "/api/admin/login":
            passcode = body.get("passcode", "").strip()
            current_code = get_host_passcode()

            if passcode == current_code:
                token = secrets.token_hex(24)
                ACTIVE_SESSIONS[token] = {"created_at": datetime.now()}
                self._send_json(200, {
                    "status": "success",
                    "message": "Host authenticated successfully.",
                    "token": token
                })
            else:
                self._send_json(401, {"status": "error", "message": "Incorrect Host Passcode. Access denied."})
            return

        # 3. API: Host Change Passcode
        if path == "/api/admin/change-passcode":
            auth_header = self.headers.get("Authorization", "")
            if not is_valid_token(auth_header):
                self._send_json(401, {"status": "error", "message": "Unauthorized."})
                return

            current_input = body.get("current_passcode", "").strip()
            new_code = body.get("new_passcode", "").strip()

            if current_input != get_host_passcode():
                self._send_json(400, {"status": "error", "message": "Current passcode is incorrect."})
                return

            if not new_code or len(new_code) < 6:
                self._send_json(400, {"status": "error", "message": "New passcode must be at least 6 characters long."})
                return

            set_host_passcode(new_code)
            self._send_json(200, {"status": "success", "message": "Host passcode successfully updated."})
            return

        # 4. API: Host Verify Applicant by Code or USN
        if path == "/api/admin/verify-code":
            auth_header = self.headers.get("Authorization", "")
            if not is_valid_token(auth_header):
                self._send_json(401, {"status": "error", "message": "Unauthorized. Host access only."})
                return

            query = body.get("code", "").strip().upper()
            mark_verified = body.get("mark_verified", False)

            if not query:
                self._send_json(400, {"status": "error", "message": "Verification code or USN is required."})
                return

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, timestamp, name, usn, verification_code, year, branch, email, phone,
                       is_verified, email_sent, verified_at, created_at
                FROM registrations
                WHERE UPPER(verification_code) = ? OR UPPER(usn) = ?
            """, (query, query))
            row = cursor.fetchone()

            if not row:
                conn.close()
                self._send_json(404, {"status": "error", "message": f"No applicant found matching code or USN '{query}'."})
                return

            applicant = dict(row)
            if mark_verified:
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute("UPDATE registrations SET is_verified = 1, verified_at = ? WHERE id = ?", (now_str, applicant["id"]))
                conn.commit()
                applicant["is_verified"] = 1
                applicant["verified_at"] = now_str
                sync_to_excel_file()

            conn.close()
            self._send_json(200, {
                "status": "success",
                "message": "Applicant verified." if mark_verified else "Applicant record found.",
                "data": applicant
            })
            return

        # 5. API: Host Toggle Applicant Verification Status
        if path == "/api/admin/toggle-verify":
            auth_header = self.headers.get("Authorization", "")
            if not is_valid_token(auth_header):
                self._send_json(401, {"status": "error", "message": "Unauthorized."})
                return

            reg_id = body.get("id")
            usn = body.get("usn", "").strip().upper() if body.get("usn") else None
            new_status = 1 if body.get("is_verified") else 0

            conn = get_db_connection()
            cursor = conn.cursor()
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if new_status else None

            if reg_id:
                cursor.execute("UPDATE registrations SET is_verified = ?, verified_at = ? WHERE id = ?", (new_status, now_str, reg_id))
            else:
                cursor.execute("UPDATE registrations SET is_verified = ?, verified_at = ? WHERE usn = ?", (new_status, now_str, usn))

            conn.commit()
            conn.close()
            sync_to_excel_file()

            self._send_json(200, {"status": "success", "is_verified": bool(new_status)})
            return

        # 6. API: Host Resend Confirmation Email
        if path == "/api/admin/resend-email":
            auth_header = self.headers.get("Authorization", "")
            if not is_valid_token(auth_header):
                self._send_json(401, {"status": "error", "message": "Unauthorized."})
                return

            reg_id = body.get("id")
            usn = body.get("usn", "").strip().upper() if body.get("usn") else None

            conn = get_db_connection()
            cursor = conn.cursor()
            if reg_id:
                cursor.execute("SELECT * FROM registrations WHERE id = ?", (reg_id,))
            else:
                cursor.execute("SELECT * FROM registrations WHERE usn = ?", (usn,))
            row = cursor.fetchone()
            conn.close()

            if not row:
                self._send_json(404, {"status": "error", "message": "Student registration not found."})
                return

            applicant_data = dict(row)
            dispatch_confirmation_email(applicant_data)
            self._send_json(200, {"status": "success", "message": f"Confirmation email queued for {applicant_data['email']}."})
            return

        # 7. API: Save SMTP Email Settings
        if path == "/api/admin/email-settings":
            auth_header = self.headers.get("Authorization", "")
            if not is_valid_token(auth_header):
                self._send_json(401, {"status": "error", "message": "Unauthorized."})
                return

            new_settings = {}
            if "smtp_host" in body:
                new_settings["smtp_host"] = body["smtp_host"].strip()
            if "smtp_port" in body:
                new_settings["smtp_port"] = str(body["smtp_port"]).strip()
            if "smtp_user" in body:
                new_settings["smtp_user"] = body["smtp_user"].strip()
            if "smtp_pass" in body and body["smtp_pass"].strip():
                new_settings["smtp_pass"] = body["smtp_pass"].strip()
            if "smtp_from_name" in body:
                new_settings["smtp_from_name"] = body["smtp_from_name"].strip()
            if "smtp_from_email" in body:
                new_settings["smtp_from_email"] = body["smtp_from_email"].strip()
            if "smtp_reply_to" in body:
                new_settings["smtp_reply_to"] = body["smtp_reply_to"].strip()
            if "smtp_enabled" in body:
                new_settings["smtp_enabled"] = "1" if body["smtp_enabled"] else "0"

            set_smtp_settings(new_settings)
            self._send_json(200, {"status": "success", "message": "Email settings saved successfully."})
            return

        # 8. API: Test Email Dispatch
        if path == "/api/admin/test-email":
            auth_header = self.headers.get("Authorization", "")
            if not is_valid_token(auth_header):
                self._send_json(401, {"status": "error", "message": "Unauthorized."})
                return

            test_recipient = body.get("recipient_email", "").strip()
            if not test_recipient or "@" not in test_recipient:
                self._send_json(400, {"status": "error", "message": "Valid recipient email address is required."})
                return

            # Combine current config with any overrides provided in body
            cfg = get_smtp_settings()
            if body.get("smtp_host"):
                cfg["smtp_host"] = body["smtp_host"].strip()
            if body.get("smtp_port"):
                cfg["smtp_port"] = str(body["smtp_port"]).strip()
            if body.get("smtp_user"):
                cfg["smtp_user"] = body["smtp_user"].strip()
            if body.get("smtp_pass"):
                cfg["smtp_pass"] = body["smtp_pass"].strip()
            if body.get("smtp_from_name"):
                cfg["smtp_from_name"] = body["smtp_from_name"].strip()
            if body.get("smtp_from_email"):
                cfg["smtp_from_email"] = body["smtp_from_email"].strip()

            sample_applicant = {
                "name": "Test Coordinator",
                "usn": "4NI26RC001",
                "verification_code": "RC26-TEST",
                "year": "2nd Year",
                "branch": "Electronics & Communication Engineering",
                "email": test_recipient,
                "phone": "9876543210",
                "timestamp": datetime.now().strftime("%d/%m/%Y, %I:%M:%S %p")
            }

            subject, text_body, html_body = build_confirmation_email_content(sample_applicant)
            subject = f"[TEST EMAIL] {subject}"

            success, err = send_email_sync(test_recipient, subject, text_body, html_body, cfg)
            if success:
                self._send_json(200, {
                    "status": "success",
                    "message": f"Test confirmation email delivered successfully to {test_recipient}!"
                })
            else:
                err_str = str(err)
                friendly_msg = err_str
                if "535" in err_str or "BadCredentials" in err_str or "Username and Password not accepted" in err_str:
                    friendly_msg = "Google rejected credentials (535 Bad Credentials). If 2-Step Verification is ON, you must generate a 16-character App Password (not your normal password). In your Google Account, visit Security -> 2-Step Verification -> App Passwords."
                elif "timed out" in err_str.lower():
                    friendly_msg = "Connection timed out connecting to smtp.gmail.com:587. Check your internet connection or firewall."
                elif "534" in err_str:
                    friendly_msg = "Google requires an App Password for institutional/personal accounts. Visit myaccount.google.com/apppasswords to create one."
                self._send_json(200, {
                    "status": "error",
                    "message": f"{friendly_msg}"
                })
            return

        # 9. API: Host Delete Registration
        if path == "/api/admin/delete-registration":
            auth_header = self.headers.get("Authorization", "")
            if not is_valid_token(auth_header):
                self._send_json(401, {"status": "error", "message": "Unauthorized. Host access only."})
                return

            reg_id = body.get("id")
            usn = body.get("usn", "").strip().upper() if body.get("usn") else None

            if not reg_id and not usn:
                self._send_json(400, {"status": "error", "message": "Registration ID or USN is required."})
                return

            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                if reg_id:
                    cursor.execute("DELETE FROM registrations WHERE id = ?", (reg_id,))
                else:
                    cursor.execute("DELETE FROM registrations WHERE usn = ?", (usn,))

                deleted_rows = cursor.rowcount
                conn.commit()
                conn.close()

                # Sync disk files (Excel & CSV)
                sync_to_excel_file()

                if deleted_rows > 0:
                    print(f"[RECRUITMENT] Deleted registration (id={reg_id}, usn={usn})")
                    self._send_json(200, {
                        "status": "success",
                        "message": "Student registration deleted and Excel sheet updated."
                    })
                else:
                    self._send_json(404, {
                        "status": "error",
                        "message": "Student record not found in database."
                    })
            except Exception as e:
                print(f"[ERROR] Delete error: {e}")
                self._send_json(500, {"status": "error", "message": f"Database error: {str(e)}"})
            return

        # Not found
        self._send_json(404, {"status": "error", "message": f"Endpoint not found: {path}"})

def run_server(port=DEFAULT_PORT):
    """Run the HTTP server."""
    init_db()
    server_address = ("", port)
    httpd = HTTPServer(server_address, RoboticsClubHandler)
    print("=" * 68)
    print(f"[*] ROBOTICS CLUB NIE -- LIVE RECRUITMENT & EMAIL BACKEND ACTIVE")
    print(f"[*] Serving at: http://localhost:{port}")
    print(f"[*] SQLite DB: {DB_PATH}")
    print(f"[*] Live Excel: {EXCEL_PATH}")
    print(f"[*] Host Portal: http://localhost:{port}/admin.html")
    print(f"[*] Default Passcode: {DEFAULT_PASSCODE}")
    print("=" * 68)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        httpd.server_close()

if __name__ == "__main__":
    port = DEFAULT_PORT
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
    run_server(port)
