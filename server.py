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
import urllib.parse
import urllib.request

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
GOOGLE_SHEET_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbxJmWqZ3WW4iuL4ag-AFd0ishWiKJlYMpZdqZz3cIHSSGEqgdn5OqcE_lxjK38hNg2s/exec"

# Active admin session tokens {token: {"created_at": datetime}}
ACTIVE_SESSIONS = {}

def sync_status_to_google_sheet(usn=None, code=None, is_verified=0):
    """Asynchronously sync candidate verification status to Google Sheets cloud."""
    if not GOOGLE_SHEET_SCRIPT_URL:
        return
    try:
        status_str = "Verified" if is_verified else "Pending"
        params = urllib.parse.urlencode({
            "action": "update_status",
            "usn": usn or "",
            "code": code or "",
            "status": status_str,
            "_t": str(int(datetime.now().timestamp()))
        })
        url = f"{GOOGLE_SHEET_SCRIPT_URL}?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "RoboticsClubNIE/2026"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            pass
    except Exception as e:
        print(f"[WARN] Cloud verification sync notice: {e}")

def sync_delete_to_google_sheet(usn=None, code=None):
    """Asynchronously delete candidate from Google Sheets cloud."""
    if not GOOGLE_SHEET_SCRIPT_URL:
        return
    try:
        params = urllib.parse.urlencode({
            "action": "delete_candidate",
            "usn": usn or "",
            "code": code or "",
            "_t": str(int(datetime.now().timestamp()))
        })
        url = f"{GOOGLE_SHEET_SCRIPT_URL}?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "RoboticsClubNIE/2026"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            pass
    except Exception as e:
        print(f"[WARN] Cloud delete sync notice: {e}")


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
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            test_score TEXT,
            is_shortlisted INTEGER DEFAULT 0,
            shortlisted_at DATETIME,
            shortlist_email_sent INTEGER DEFAULT 0,
            shortlist_email_error TEXT,
            shortlist_email_sent_at DATETIME,
            shortlist_notes TEXT
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
        ("test_score", "ALTER TABLE registrations ADD COLUMN test_score TEXT"),
        ("is_shortlisted", "ALTER TABLE registrations ADD COLUMN is_shortlisted INTEGER DEFAULT 0"),
        ("shortlisted_at", "ALTER TABLE registrations ADD COLUMN shortlisted_at DATETIME"),
        ("shortlist_email_sent", "ALTER TABLE registrations ADD COLUMN shortlist_email_sent INTEGER DEFAULT 0"),
        ("shortlist_email_error", "ALTER TABLE registrations ADD COLUMN shortlist_email_error TEXT"),
        ("shortlist_email_sent_at", "ALTER TABLE registrations ADD COLUMN shortlist_email_sent_at DATETIME"),
        ("shortlist_notes", "ALTER TABLE registrations ADD COLUMN shortlist_notes TEXT"),
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

def build_shortlist_email_content(applicant):
    """
    Constructs subject, plain-text body, and responsive HTML email for candidates
    shortlisted for the Interview & Domain Evaluation Round.
    Explicitly informs the candidate that panel and location details will be sent shortly through WhatsApp.
    """
    name = applicant.get("name", "Applicant")
    usn = applicant.get("usn", "—")
    code = applicant.get("verification_code", "RC26-PENDING")
    year = applicant.get("year", "—")
    branch = applicant.get("branch", "—")
    email = applicant.get("email", "—")
    phone = applicant.get("phone", "—")
    test_score = str(applicant.get("test_score") or "").strip()

    subject = f"Interview Shortlist: Recruitment 2026 — Robotics Club NIE [USN: {usn}]"

    score_line = f"• Test Evaluation:   {test_score}\n" if test_score else ""

    text_body = f"""====================================================
ROBOTICS CLUB — THE NATIONAL INSTITUTE OF ENGINEERING, MYSURU
MEMBER RECRUITMENT 2026 • INTERVIEW SHORTLIST NOTIFICATION
====================================================

Dear {name},

Congratulations!
Based on your evaluation in the Recruitment 2026 test, the Core Committee of The Robotics Club @ NIE is pleased to inform you that you have been SHORTLISTED FOR THE INTERVIEW ROUND!

----------------------------------------------------
IMPORTANT: INTERVIEW PANEL & LOCATION NOTICE
----------------------------------------------------
We will inform you of your allotted Interview Panel and Venue Location shortly through WhatsApp on your registered contact number:
>>> {phone} <<<

Please ensure your WhatsApp is active and check your incoming messages regularly for your panel schedule and reporting time slot.

----------------------------------------------------
CANDIDATE INFORMATION:
----------------------------------------------------
• Full Name:         {name}
• USN:               {usn}
• Verification Code: {code}
• Year of Study:     {year}
• Department/Branch: {branch}
• Contact Number:    {phone}
{score_line}• Selection Status:  Shortlisted for Interview Round

----------------------------------------------------
INTERVIEW ROUND INSTRUCTIONS:
----------------------------------------------------
1. Verification: Bring your official College ID Card and keep your Verification Code ({code}) handy.
2. Domain Evaluation: Be prepared to discuss your ideas, enthusiasm, and domain interests:
   - Mechanical & CAD (SolidWorks, Fusion 360, 3D printing)
   - Embedded Systems & Electronics (Microcontrollers, Sensors, Circuits)
   - Autonomous Systems, AI & Software (ROS, Python/C++, Computer Vision)
   - Media, Web Development & Event Management
3. Projects & Work: If you have built any previous projects, software code, CAD models, or creative portfolios, feel free to present them to the interview panel.
4. Punctuality: Please arrive at least 10 minutes prior to your allotted time slot once announced on WhatsApp.

For inquiries or questions, contact us:
• Email: roboticsclubnie@nie.ac.in
• Instagram: https://instagram.com/roboticsclub_nie
• Website: https://roboticsclubnie.in

We look forward to meeting you in the interview round and discussing your journey with The Robotics Club!

Warm regards,
Core Recruitment Committee & Faculty Advisors
The Robotics Club
The National Institute of Engineering, Mysuru
====================================================
"""

    score_row_html = f"""
    <tr>
      <td style="padding: 10px 16px; border-bottom: 1px solid rgba(255, 255, 255, 0.06); font-size: 13px; color: #64748b;">Test Evaluation Result</td>
      <td style="padding: 10px 16px; border-bottom: 1px solid rgba(255, 255, 255, 0.06); font-size: 13px; color: #10b981; font-weight: 700;">{test_score}</td>
    </tr>
    """ if test_score else ""

    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Shortlisted for Interview — Robotics Club NIE</title>
</head>
<body style="margin: 0; padding: 0; background-color: #000814; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #f1f5f9;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color: #000814; width: 100%; padding: 40px 10px;">
    <tr>
      <td align="center">
        <!-- Main Container -->
        <table role="presentation" width="100%" style="max-width: 620px; background: #001226; border: 1px solid rgba(0, 234, 255, 0.35); border-radius: 16px; overflow: hidden; box-shadow: 0 12px 45px rgba(0, 234, 255, 0.2);" cellspacing="0" cellpadding="0" border="0">
          
          <!-- Header Banner -->
          <tr>
            <td style="background: linear-gradient(135deg, #001a3d 0%, #002b66 60%, #001226 100%); padding: 36px 30px; text-align: center; border-bottom: 2px solid #00eaff;">
              <div style="display: inline-block; padding: 5px 16px; background: rgba(16, 185, 129, 0.15); border: 1px solid #10b981; border-radius: 20px; color: #34d399; font-size: 11px; font-weight: 700; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 12px;">
                ⭐ Official Interview Shortlist • Recruitment 2026
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
              <p style="margin: 0 0 24px 0; font-size: 15px; line-height: 1.6; color: #cbd5e1;">
                Congratulations! Based on your performance and evaluation in the Recruitment 2026 test, we are pleased to inform you that you have been <strong style="color: #34d399;">shortlisted for the Interview &amp; Domain Evaluation Round</strong> at The Robotics Club, NIE Mysuru.
              </p>

              <!-- CRITICAL WHATSAPP & PANEL NOTICE BOX -->
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin: 28px 0; background: linear-gradient(135deg, rgba(16, 185, 129, 0.12) 0%, rgba(0, 43, 91, 0.85) 100%); border: 2px solid #10b981; border-radius: 12px;">
                <tr>
                  <td style="padding: 24px 22px;">
                    <div style="font-size: 12px; font-weight: 800; letter-spacing: 1.5px; text-transform: uppercase; color: #34d399; margin-bottom: 8px;">
                      📢 IMPORTANT INTERVIEW NOTICE
                    </div>
                    <div style="font-size: 16px; font-weight: 700; color: #ffffff; line-height: 1.5; margin-bottom: 10px;">
                      We will inform you of your allotted interview panel and venue location shortly through WhatsApp.
                    </div>
                    <div style="font-size: 13.5px; color: #cbd5e1; line-height: 1.6;">
                      Our recruitment coordinators will message your registered contact number <strong style="color: #00eaff;">{phone}</strong> with your assigned interview panel, venue/room location, and exact time slot. Please keep your WhatsApp notifications active.
                    </div>
                  </td>
                </tr>
              </table>

              <!-- Candidate Summary Details -->
              <div style="margin-bottom: 12px; font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: #00eaff;">
                Candidate Information
              </div>
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background: rgba(0, 20, 42, 0.6); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px; margin-bottom: 28px;">
                <tr>
                  <td style="padding: 10px 16px; border-bottom: 1px solid rgba(255, 255, 255, 0.06); font-size: 13px; color: #64748b; width: 38%;">Candidate Name</td>
                  <td style="padding: 10px 16px; border-bottom: 1px solid rgba(255, 255, 255, 0.06); font-size: 13px; color: #ffffff; font-weight: 600;">{name}</td>
                </tr>
                <tr>
                  <td style="padding: 10px 16px; border-bottom: 1px solid rgba(255, 255, 255, 0.06); font-size: 13px; color: #64748b;">USN</td>
                  <td style="padding: 10px 16px; border-bottom: 1px solid rgba(255, 255, 255, 0.06); font-size: 13px; color: #00eaff; font-weight: 700; font-family: monospace;">{usn}</td>
                </tr>
                <tr>
                  <td style="padding: 10px 16px; border-bottom: 1px solid rgba(255, 255, 255, 0.06); font-size: 13px; color: #64748b;">Verification Code</td>
                  <td style="padding: 10px 16px; border-bottom: 1px solid rgba(255, 255, 255, 0.06); font-size: 13px; color: #ffffff; font-weight: 700; font-family: monospace;">{code}</td>
                </tr>
                <tr>
                  <td style="padding: 10px 16px; border-bottom: 1px solid rgba(255, 255, 255, 0.06); font-size: 13px; color: #64748b;">Year &amp; Department</td>
                  <td style="padding: 10px 16px; border-bottom: 1px solid rgba(255, 255, 255, 0.06); font-size: 13px; color: #e2e8f0;">{year} &bull; {branch}</td>
                </tr>
                <tr>
                  <td style="padding: 10px 16px; border-bottom: 1px solid rgba(255, 255, 255, 0.06); font-size: 13px; color: #64748b;">Registered WhatsApp</td>
                  <td style="padding: 10px 16px; border-bottom: 1px solid rgba(255, 255, 255, 0.06); font-size: 13px; color: #34d399; font-weight: 600;">{phone}</td>
                </tr>
                {score_row_html}
                <tr>
                  <td style="padding: 10px 16px; font-size: 13px; color: #64748b;">Interview Status</td>
                  <td style="padding: 10px 16px; font-size: 13px; color: #38bdf8; font-weight: 600;">Shortlisted &bull; Schedule Pending via WhatsApp</td>
                </tr>
              </table>

              <!-- Interview Preparation Tips -->
              <div style="background: rgba(0, 234, 255, 0.05); border-left: 3px solid #00eaff; padding: 18px; border-radius: 6px; margin-bottom: 28px;">
                <div style="font-size: 13.5px; font-weight: 700; color: #00eaff; margin-bottom: 8px;">Important Guidelines for the Interview Round:</div>
                <ul style="margin: 0; padding-left: 18px; font-size: 13px; color: #cbd5e1; line-height: 1.6;">
                  <li>Carry your official <strong>College ID Card</strong> for verification.</li>
                  <li>Keep your verification code (<strong style="color: #ffffff;">{code}</strong>) accessible.</li>
                  <li>Feel free to present or showcase any past projects, hardware builds, software repositories, CAD models, or creative portfolios.</li>
                  <li>Domains evaluated: Mechanical &amp; CAD, Embedded &amp; IoT, Autonomous Bots/AI/ROS, and Web &amp; Media.</li>
                </ul>
              </div>

              <p style="margin: 0 0 20px 0; font-size: 14px; line-height: 1.6; color: #94a3b8;">
                We look forward to meeting you and having an exciting technical discussion. Best of luck!
              </p>

              <!-- Button CTA -->
              <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin: 0 auto 10px auto;">
                <tr>
                  <td style="border-radius: 8px; background: linear-gradient(135deg, #10b981 0%, #0077b6 100%); text-align: center;">
                    <a href="https://roboticsclubnie.in" target="_blank" style="background: linear-gradient(135deg, #10b981 0%, #0077b6 100%); border: 1px solid #10b981; padding: 12px 28px; color: #ffffff; text-decoration: none; font-size: 14px; font-weight: 700; display: inline-block; border-radius: 8px; letter-spacing: 0.5px;">
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

def dispatch_shortlist_email(applicant_dict):
    """
    Dispatches professional interview shortlist email to an applicant in a background thread.
    Updates shortlist_email_sent, shortlist_email_sent_at, shortlist_email_error in SQLite.
    """
    def _worker():
        email = applicant_dict.get("email")
        usn = applicant_dict.get("usn")
        code = applicant_dict.get("verification_code")

        smtp_cfg = get_smtp_settings()
        is_enabled = smtp_cfg.get("smtp_enabled", "1") != "0"
        has_credentials = bool(smtp_cfg.get("smtp_user") and smtp_cfg.get("smtp_pass"))

        if not is_enabled or not has_credentials:
            err_msg = "SMTP credentials not configured in Host Portal"
            print(f"[SHORTLIST EMAIL NOTICE] {err_msg}. Cannot send interview email to {email} ({usn}).")
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("UPDATE registrations SET shortlist_email_sent = 0, shortlist_email_error = ? WHERE usn = ?", (err_msg, usn))
            conn.commit()
            conn.close()
            return

        subject, text_body, html_body = build_shortlist_email_content(applicant_dict)
        success, err = send_email_sync(email, subject, text_body, html_body, smtp_cfg)

        conn = get_db_connection()
        c = conn.cursor()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if success:
            print(f"[SHORTLIST EMAIL SUCCESS] Interview shortlist email delivered to {email} (USN: {usn})")
            c.execute("UPDATE registrations SET shortlist_email_sent = 1, shortlist_email_sent_at = ?, shortlist_email_error = NULL WHERE usn = ?", (now_str, usn))
        else:
            print(f"[SHORTLIST EMAIL ERROR] Failed to send interview email to {email}: {err}")
            c.execute("UPDATE registrations SET shortlist_email_sent = 0, shortlist_email_error = ? WHERE usn = ?", (str(err)[:250], usn))
        conn.commit()
        conn.close()
        sync_to_excel_file()

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

def dispatch_shortlist_emails_batch(applicant_dicts):
    """
    Dispatches professional interview shortlist emails to a batch of candidates sequentially in background thread.
    """
    def _worker():
        smtp_cfg = get_smtp_settings()
        is_enabled = smtp_cfg.get("smtp_enabled", "1") != "0"
        has_credentials = bool(smtp_cfg.get("smtp_user") and smtp_cfg.get("smtp_pass"))

        if not is_enabled or not has_credentials:
            print("[SHORTLIST EMAIL NOTICE] Batch send aborted: SMTP not configured in Host Portal.")
            return

        for cand in applicant_dicts:
            email = cand.get("email")
            usn = cand.get("usn")
            if not email or "@" not in email:
                continue
            subject, text_body, html_body = build_shortlist_email_content(cand)
            success, err = send_email_sync(email, subject, text_body, html_body, smtp_cfg)

            conn = get_db_connection()
            c = conn.cursor()
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if success:
                print(f"[BATCH SHORTLIST SUCCESS] Delivered interview email to {email} (USN: {usn})")
                c.execute("UPDATE registrations SET shortlist_email_sent = 1, shortlist_email_sent_at = ?, shortlist_email_error = NULL WHERE usn = ?", (now_str, usn))
            else:
                print(f"[BATCH SHORTLIST ERROR] Failed to deliver to {email} (USN: {usn}): {err}")
                c.execute("UPDATE registrations SET shortlist_email_sent = 0, shortlist_email_error = ? WHERE usn = ?", (str(err)[:250], usn))
            conn.commit()
            conn.close()

        sync_to_excel_file()

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

# ==============================================================================
# EXCEL & CSV SYNCHRONIZATION
# ==============================================================================

def sync_to_excel_file():
    """
    Generate or update recruitment_registrations.xlsx and .csv directly on disk,
    including Verification Code, Status, Test Score, and Shortlist flags.
    Also creates a dedicated 'Interview Shortlist' sheet for coordinators.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, timestamp, name, usn, verification_code, year, branch, email, phone,
               is_verified, email_sent, email_error,
               test_score, is_shortlisted, shortlisted_at, shortlist_email_sent, shortlist_email_error
        FROM registrations
        ORDER BY id ASC
    """)
    rows = cursor.fetchall()
    conn.close()

    # 1. Update CSV file
    try:
        with open(CSV_PATH, "w", encoding="utf-8") as f:
            f.write("SL No.,Timestamp,Full Name,USN,Verification Code,Year of Study,Branch,Email ID,Phone Number,Test Score,Status,Shortlisted,Interview Email,Shortlisted Date\n")
            for idx, r in enumerate(rows, start=1):
                clean_name = r["name"].replace('"', '""')
                clean_branch = r["branch"].replace('"', '""')
                v_code = r["verification_code"] or "—"
                score_str = (r["test_score"] or "—").replace('"', '""')
                status_str = "Verified" if r["is_verified"] else "Pending"
                shortlist_str = "Shortlisted" if r["is_shortlisted"] else "No"
                int_email_str = "Delivered" if r["shortlist_email_sent"] else ("Pending" if not r["shortlist_email_error"] else f"Error: {r['shortlist_email_error'][:20]}")
                s_date = r["shortlisted_at"] or "—"
                f.write(f'{idx},"{r["timestamp"]}","{clean_name}","{r["usn"]}","{v_code}","{r["year"]}","{clean_branch}","{r["email"]}","{r["phone"]}","{score_str}","{status_str}","{shortlist_str}","{int_email_str}","{s_date}"\n')
    except Exception as e:
        print(f"[WARN] Error updating CSV file: {e}")

    # 2. Update native .xlsx file if openpyxl is available
    if not OPENPYXL_AVAILABLE:
        return

    try:
        wb = openpyxl.Workbook()
        
        # Sheet 1: Master Roster
        ws = wb.active
        ws.title = "Recruitment 2026"
        ws.views.sheetView[0].showGridLines = True

        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="002145", end_color="002145", fill_type="solid")
        header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        headers = [
            "SL No.", "Registered At", "Full Name", "USN", "Verification Code",
            "Year of Study", "Branch", "Email ID", "Phone Number", "Test Score",
            "Status", "Shortlisted", "Interview Email", "Shortlisted Date"
        ]
        ws.append(headers)

        for col_num in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_num)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment

        ws.row_dimensions[1].height = 28

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
        
        shortlisted_fill = PatternFill(start_color="FFF8E1", end_color="FFF8E1", fill_type="solid")
        shortlisted_font = Font(name="Calibri", size=10, bold=True, color="B45309")
        score_font = Font(name="Calibri", size=10, bold=True, color="047857")

        for idx, r in enumerate(rows, start=1):
            v_code = r["verification_code"] or "—"
            status_str = "Verified" if r["is_verified"] else "Pending"
            shortlist_str = "⭐ Shortlisted" if r["is_shortlisted"] else "No"
            int_email_str = "Delivered" if r["shortlist_email_sent"] else ("Pending" if not r["shortlist_email_error"] else "Failed")
            test_sc = r["test_score"] or "—"
            s_date = r["shortlisted_at"] or "—"

            row_data = [
                idx, r["timestamp"], r["name"], r["usn"], v_code,
                r["year"], r["branch"], r["email"], r["phone"],
                test_sc, status_str, shortlist_str, int_email_str, s_date
            ]
            ws.append(row_data)
            row_num = idx + 1
            ws.row_dimensions[row_num].height = 20

            base_row_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid") if idx % 2 == 0 else None

            for col_num in range(1, len(row_data) + 1):
                cell = ws.cell(row=row_num, column=col_num)
                cell.border = thin_border
                if base_row_fill:
                    cell.fill = base_row_fill

                if col_num in (1, 6, 10, 11, 12, 13):
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                elif col_num in (2, 4, 9, 14):
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                elif col_num == 5:
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                    cell.font = code_font
                    cell.fill = code_fill
                else:
                    cell.alignment = Alignment(horizontal="left", vertical="center")

                if col_num == 10 and test_sc != "—":
                    cell.font = score_font

                if col_num == 11:
                    cell.fill = verified_fill if r["is_verified"] else pending_fill
                    cell.font = verified_font if r["is_verified"] else pending_font

                if col_num == 12 and r["is_shortlisted"]:
                    cell.fill = shortlisted_fill
                    cell.font = shortlisted_font

        col_widths = {
            1: 8, 2: 24, 3: 28, 4: 16, 5: 20, 6: 15,
            7: 34, 8: 32, 9: 18, 10: 16, 11: 14, 12: 18, 13: 18, 14: 20
        }
        for col_idx, width in col_widths.items():
            ws.column_dimensions[get_column_letter(col_idx)].width = width

        # Sheet 2: Dedicated "Interview Shortlist"
        shortlisted_rows = [r for r in rows if r["is_shortlisted"]]
        ws_short = wb.create_sheet(title="Interview Shortlist")
        ws_short.views.sheetView[0].showGridLines = True

        short_headers = [
            "SL No.", "Full Name", "USN", "Verification Code", "Year",
            "Branch", "Email Address", "WhatsApp Phone", "Test Score",
            "Shortlisted Date", "Interview Email"
        ]
        ws_short.append(short_headers)

        short_header_fill = PatternFill(start_color="0F5132", end_color="0F5132", fill_type="solid")
        for col_num in range(1, len(short_headers) + 1):
            cell = ws_short.cell(row=1, column=col_num)
            cell.font = header_font
            cell.fill = short_header_fill
            cell.alignment = header_alignment

        ws_short.row_dimensions[1].height = 28

        for s_idx, sr in enumerate(shortlisted_rows, start=1):
            s_vcode = sr["verification_code"] or "—"
            s_score = sr["test_score"] or "—"
            s_email_status = "Delivered" if sr["shortlist_email_sent"] else ("Pending" if not sr["shortlist_email_error"] else "Failed")
            s_row = [
                s_idx, sr["name"], sr["usn"], s_vcode, sr["year"],
                sr["branch"], sr["email"], sr["phone"], s_score,
                sr["shortlisted_at"] or "—", s_email_status
            ]
            ws_short.append(s_row)
            r_num = s_idx + 1
            ws_short.row_dimensions[r_num].height = 20
            for col_num in range(1, len(s_row) + 1):
                c = ws_short.cell(row=r_num, column=col_num)
                c.border = thin_border
                if col_num in (1, 3, 4, 5, 8, 9, 10, 11):
                    c.alignment = Alignment(horizontal="center", vertical="center")
                else:
                    c.alignment = Alignment(horizontal="left", vertical="center")

        short_widths = {1: 8, 2: 28, 3: 16, 4: 20, 5: 14, 6: 34, 7: 32, 8: 18, 9: 16, 10: 20, 11: 18}
        for col_idx, width in short_widths.items():
            ws_short.column_dimensions[get_column_letter(col_idx)].width = width

        wb.save(EXCEL_PATH)
    except Exception as e:
        print(f"[WARN] Error updating Excel file: {e}")

def generate_shortlisted_excel_file():
    """
    Generates a dedicated Excel export containing only shortlisted candidates.
    Returns path to file.
    """
    sync_to_excel_file()
    return EXCEL_PATH

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
                       is_verified, email_sent, email_error, verified_at, created_at,
                       test_score, is_shortlisted, shortlisted_at, shortlist_email_sent, shortlist_email_error, shortlist_email_sent_at, shortlist_notes
                FROM registrations
                ORDER BY id DESC
            """)
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()

            shortlisted_count = sum(1 for r in rows if r.get("is_shortlisted"))
            self._send_json(200, {
                "status": "success",
                "count": len(rows),
                "shortlisted_count": shortlisted_count,
                "data": rows
            })
            return

        # 1b. API: Get shortlisted candidates only (Host only)
        if path == "/api/admin/shortlisted":
            auth_header = self.headers.get("Authorization", "")
            if not is_valid_token(auth_header):
                self._send_json(401, {"status": "error", "message": "Unauthorized. Host session invalid."})
                return

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, timestamp, name, usn, verification_code, year, branch, email, phone,
                       is_verified, email_sent, email_error, verified_at, created_at,
                       test_score, is_shortlisted, shortlisted_at, shortlist_email_sent, shortlist_email_error, shortlist_email_sent_at, shortlist_notes
                FROM registrations
                WHERE is_shortlisted = 1
                ORDER BY shortlisted_at DESC, id DESC
            """)
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()

            self._send_json(200, {
                "status": "success",
                "count": len(rows),
                "data": rows
            })
            return

        # 1c. API: Lightweight live sync polling for all devices (Host only)
        if path == "/api/admin/live-sync":
            auth_header = self.headers.get("Authorization", "")
            if not is_valid_token(auth_header):
                self._send_json(401, {"status": "error", "message": "Unauthorized."})
                return

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, timestamp, name, usn, verification_code, year, branch, email, phone,
                       is_verified, email_sent, email_error, verified_at, created_at,
                       test_score, is_shortlisted, shortlisted_at, shortlist_email_sent, shortlist_email_error, shortlist_email_sent_at, shortlist_notes
                FROM registrations
                ORDER BY id DESC
            """)
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()

            self._send_json(200, {
                "status": "success",
                "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_count": len(rows),
                "shortlisted_count": sum(1 for r in rows if r.get("is_shortlisted")),
                "verified_count": sum(1 for r in rows if r.get("is_verified")),
                "data": rows
            })
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

        # 4. API: Host Sync with Google Sheet Cloud
        if path == "/api/admin/sync-cloud":
            auth_header = self.headers.get("Authorization", "")
            if not is_valid_token(auth_header):
                self._send_json(401, {"status": "error", "message": "Unauthorized. Host access only."})
                return

            try:
                req = urllib.request.Request(
                    GOOGLE_SHEET_SCRIPT_URL,
                    headers={"User-Agent": "RoboticsClubNIE/2026"}
                )
                with urllib.request.urlopen(req, timeout=12) as response:
                    raw_data = response.read().decode("utf-8")
                    sheet_json = json.loads(raw_data) if raw_data else {}

                if sheet_json.get("status") != "success" or not isinstance(sheet_json.get("data"), list):
                    msg = sheet_json.get("message", "Google Sheet script returned unformatted response.")
                    self._send_json(200, {
                        "status": "notice",
                        "message": f"Cloud webhook active, but sheet rows were not returned ({msg}). Please ensure the updated Apps Script doGet is deployed.",
                        "raw": sheet_json
                    })
                    return

                cloud_rows = sheet_json.get("data", [])
                conn = get_db_connection()
                cursor = conn.cursor()
                synced_count = 0

                for item in cloud_rows:
                    name = str(item.get("name", "")).strip()
                    usn = str(item.get("usn", "")).strip().upper()
                    if not name or not usn:
                        continue

                    year = str(item.get("year", "")).strip()
                    branch = str(item.get("branch", "")).strip()
                    email = str(item.get("email", "")).strip()
                    phone = str(item.get("phone", "")).strip()
                    timestamp = str(item.get("timestamp", "")).strip() or datetime.now().strftime("%d/%m/%Y, %I:%M:%S %p")
                    vcode = str(item.get("verification_code", "")).strip().upper()
                    is_v = 1 if item.get("is_verified") else 0

                    if not vcode or not vcode.startswith("RC26-"):
                        cursor.execute("SELECT verification_code FROM registrations WHERE usn = ?", (usn,))
                        exist_row = cursor.fetchone()
                        if exist_row and exist_row["verification_code"]:
                            vcode = exist_row["verification_code"]
                        else:
                            vcode = generate_unique_code(cursor)

                    cursor.execute("""
                        INSERT INTO registrations (timestamp, name, usn, verification_code, year, branch, email, phone, is_verified, email_sent)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                        ON CONFLICT(usn) DO UPDATE SET
                            name=excluded.name,
                            year=COALESCE(NULLIF(excluded.year, ''), registrations.year),
                            branch=COALESCE(NULLIF(excluded.branch, ''), registrations.branch),
                            email=COALESCE(NULLIF(excluded.email, ''), registrations.email),
                            phone=COALESCE(NULLIF(excluded.phone, ''), registrations.phone),
                            verification_code=COALESCE(NULLIF(excluded.verification_code, ''), registrations.verification_code),
                            is_verified=excluded.is_verified,
                            email_sent=1
                    """, (timestamp, name, usn, vcode, year, branch, email, phone, is_v))
                    synced_count += 1

                conn.commit()
                conn.close()
                sync_to_excel_file()

                self._send_json(200, {
                    "status": "success",
                    "message": f"Synchronized {synced_count} applicant records from Google Sheet to SQLite & Excel.",
                    "count": synced_count
                })
            except Exception as e:
                self._send_json(500, {"status": "error", "message": f"Cloud sync error: {str(e)}"})
            return

        # 5. API: Public live count
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
                       is_verified, email_sent, verified_at, created_at,
                       test_score, is_shortlisted, shortlisted_at
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

                # Sync to Google Sheet cloud asynchronously
                threading.Thread(
                    target=sync_status_to_google_sheet,
                    args=(applicant.get("usn"), applicant.get("verification_code"), 1),
                    daemon=True
                ).start()

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

            vcode = body.get("verification_code")
            if reg_id:
                cursor.execute("UPDATE registrations SET is_verified = ?, verified_at = ? WHERE id = ?", (new_status, now_str, reg_id))
                cursor.execute("SELECT usn, verification_code FROM registrations WHERE id = ?", (reg_id,))
                row = cursor.fetchone()
                if row:
                    usn = row["usn"]
                    vcode = row["verification_code"]
            else:
                cursor.execute("UPDATE registrations SET is_verified = ?, verified_at = ? WHERE usn = ?", (new_status, now_str, usn))
                if not vcode:
                    cursor.execute("SELECT verification_code FROM registrations WHERE usn = ?", (usn,))
                    row = cursor.fetchone()
                    vcode = row["verification_code"] if row else None

            conn.commit()
            conn.close()
            sync_to_excel_file()

            # Background cloud sync to Google Sheets
            threading.Thread(
                target=sync_status_to_google_sheet,
                args=(usn, vcode, new_status),
                daemon=True
            ).start()

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

                target_row = None
                if reg_id:
                    cursor.execute("SELECT usn, verification_code FROM registrations WHERE id = ?", (reg_id,))
                    target_row = cursor.fetchone()
                elif usn:
                    cursor.execute("SELECT usn, verification_code FROM registrations WHERE usn = ?", (usn,))
                    target_row = cursor.fetchone()

                if reg_id:
                    cursor.execute("DELETE FROM registrations WHERE id = ?", (reg_id,))
                else:
                    cursor.execute("DELETE FROM registrations WHERE usn = ?", (usn,))

                deleted_rows = cursor.rowcount
                conn.commit()
                conn.close()

                # Sync disk files (Excel & CSV)
                sync_to_excel_file()

                if target_row:
                    t_usn = target_row["usn"]
                    t_code = target_row["verification_code"]
                    threading.Thread(
                        target=sync_delete_to_google_sheet,
                        args=(t_usn, t_code),
                        daemon=True
                    ).start()

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

        # 10. API: Host Batch Import (from Google Sheet, Sent Emails, or CSV)
        if path == "/api/admin/import-batch":
            auth_header = self.headers.get("Authorization", "")
            if not is_valid_token(auth_header):
                self._send_json(401, {"status": "error", "message": "Unauthorized. Host access only."})
                return

            items = body.get("registrations", [])
            if not isinstance(items, list) or len(items) == 0:
                self._send_json(400, {"status": "error", "message": "A non-empty 'registrations' list is required."})
                return

            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                imported_count = 0

                for item in items:
                    name = str(item.get("name", "")).strip()
                    usn = str(item.get("usn", "")).strip().upper()
                    if not name or not usn:
                        continue

                    year = str(item.get("year", "")).strip()
                    branch = str(item.get("branch", "")).strip()
                    email = str(item.get("email", "")).strip()
                    phone = str(item.get("phone", "")).strip()
                    timestamp = str(item.get("timestamp", "")).strip() or datetime.now().strftime("%d/%m/%Y, %I:%M:%S %p")
                    vcode = str(item.get("verification_code", "")).strip().upper()
                    is_v = 1 if item.get("is_verified") else 0
                    e_sent = 1 if item.get("email_sent") or item.get("email_sent") is None else 0

                    if not vcode or not vcode.startswith("RC26-"):
                        cursor.execute("SELECT verification_code FROM registrations WHERE usn = ?", (usn,))
                        exist_row = cursor.fetchone()
                        if exist_row and exist_row["verification_code"]:
                            vcode = exist_row["verification_code"]
                        else:
                            vcode = generate_unique_code(cursor)

                    cursor.execute("""
                        INSERT INTO registrations (timestamp, name, usn, verification_code, year, branch, email, phone, is_verified, email_sent)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(usn) DO UPDATE SET
                            name=excluded.name,
                            year=COALESCE(NULLIF(excluded.year, ''), registrations.year),
                            branch=COALESCE(NULLIF(excluded.branch, ''), registrations.branch),
                            email=COALESCE(NULLIF(excluded.email, ''), registrations.email),
                            phone=COALESCE(NULLIF(excluded.phone, ''), registrations.phone),
                            verification_code=COALESCE(NULLIF(excluded.verification_code, ''), registrations.verification_code),
                            is_verified=excluded.is_verified,
                            email_sent=MAX(registrations.email_sent, excluded.email_sent)
                    """, (timestamp, name, usn, vcode, year, branch, email, phone, is_v, e_sent))
                    imported_count += 1

                conn.commit()
                conn.close()

                # Sync to disk files (.xlsx & .csv)
                sync_to_excel_file()

                print(f"[RECRUITMENT] Imported/synced {imported_count} registrations into database.")
                self._send_json(200, {
                    "status": "success",
                    "message": f"Successfully imported and synced {imported_count} applicants.",
                    "count": imported_count
                })
            except Exception as e:
                print(f"[ERROR] Import batch error: {e}")
                self._send_json(500, {"status": "error", "message": f"Database import error: {str(e)}"})
            return

        # 11. API: Host Shortlist Candidate for Interview
        if path == "/api/admin/shortlist":
            auth_header = self.headers.get("Authorization", "")
            if not is_valid_token(auth_header):
                self._send_json(401, {"status": "error", "message": "Unauthorized. Host access only."})
                return

            reg_id = body.get("id")
            usn = body.get("usn", "").strip().upper() if body.get("usn") else None
            is_shortlisted = 1 if body.get("is_shortlisted", True) else 0
            test_score = body.get("test_score")
            notes = body.get("notes")

            if not reg_id and not usn:
                self._send_json(400, {"status": "error", "message": "Candidate USN or ID is required."})
                return

            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                if reg_id:
                    cursor.execute("SELECT * FROM registrations WHERE id = ?", (reg_id,))
                else:
                    cursor.execute("SELECT * FROM registrations WHERE usn = ?", (usn,))
                target = cursor.fetchone()

                if not target:
                    conn.close()
                    self._send_json(404, {"status": "error", "message": f"Candidate not found ({usn or reg_id})."})
                    return

                cand_id = target["id"]
                cand_usn = target["usn"]
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if is_shortlisted else None

                updates = ["is_shortlisted = ?", "shortlisted_at = ?"]
                params = [is_shortlisted, now_str]

                if test_score is not None:
                    updates.append("test_score = ?")
                    params.append(str(test_score).strip())

                if notes is not None:
                    updates.append("shortlist_notes = ?")
                    params.append(str(notes).strip())

                params.append(cand_id)
                cursor.execute(f"UPDATE registrations SET {', '.join(updates)} WHERE id = ?", params)
                conn.commit()

                cursor.execute("SELECT * FROM registrations WHERE id = ?", (cand_id,))
                updated_cand = dict(cursor.fetchone())
                conn.close()

                sync_to_excel_file()

                msg = f"Candidate {updated_cand['name']} ({cand_usn}) shortlisted for interview." if is_shortlisted else f"Removed {updated_cand['name']} ({cand_usn}) from shortlist."
                print(f"[SHORTLIST] {msg}")

                self._send_json(200, {
                    "status": "success",
                    "message": msg,
                    "is_shortlisted": is_shortlisted,
                    "data": updated_cand
                })
            except Exception as e:
                print(f"[ERROR] Shortlist error: {e}")
                self._send_json(500, {"status": "error", "message": f"Database error: {str(e)}"})
            return

        # 12. API: Host Remove from Shortlist (Mistake undo button)
        if path == "/api/admin/remove-from-shortlist":
            auth_header = self.headers.get("Authorization", "")
            if not is_valid_token(auth_header):
                self._send_json(401, {"status": "error", "message": "Unauthorized. Host access only."})
                return

            reg_id = body.get("id")
            usn = body.get("usn", "").strip().upper() if body.get("usn") else None

            if not reg_id and not usn:
                self._send_json(400, {"status": "error", "message": "Candidate USN or ID is required."})
                return

            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                if reg_id:
                    cursor.execute("SELECT * FROM registrations WHERE id = ?", (reg_id,))
                else:
                    cursor.execute("SELECT * FROM registrations WHERE usn = ?", (usn,))
                target = cursor.fetchone()

                if not target:
                    conn.close()
                    self._send_json(404, {"status": "error", "message": "Candidate not found."})
                    return

                cand_id = target["id"]
                cand_name = target["name"]
                cand_usn = target["usn"]

                cursor.execute("UPDATE registrations SET is_shortlisted = 0, shortlisted_at = NULL WHERE id = ?", (cand_id,))
                conn.commit()
                conn.close()

                sync_to_excel_file()
                print(f"[SHORTLIST REMOVE] Removed {cand_name} ({cand_usn}) from interview shortlist.")

                self._send_json(200, {
                    "status": "success",
                    "message": f"Successfully removed {cand_name} ({cand_usn}) from interview shortlist.",
                    "usn": cand_usn
                })
            except Exception as e:
                print(f"[ERROR] Remove shortlist error: {e}")
                self._send_json(500, {"status": "error", "message": f"Database error: {str(e)}"})
            return

        # 13. API: Host Update Test Score / Result
        if path == "/api/admin/update-test-score":
            auth_header = self.headers.get("Authorization", "")
            if not is_valid_token(auth_header):
                self._send_json(401, {"status": "error", "message": "Unauthorized."})
                return

            reg_id = body.get("id")
            usn = body.get("usn", "").strip().upper() if body.get("usn") else None
            test_score = str(body.get("test_score", "")).strip()

            if not reg_id and not usn:
                self._send_json(400, {"status": "error", "message": "Candidate USN or ID is required."})
                return

            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                if reg_id:
                    cursor.execute("UPDATE registrations SET test_score = ? WHERE id = ?", (test_score, reg_id))
                    cursor.execute("SELECT * FROM registrations WHERE id = ?", (reg_id,))
                else:
                    cursor.execute("UPDATE registrations SET test_score = ? WHERE usn = ?", (test_score, usn))
                    cursor.execute("SELECT * FROM registrations WHERE usn = ?", (usn,))
                updated_row = cursor.fetchone()
                conn.commit()
                conn.close()

                sync_to_excel_file()

                self._send_json(200, {
                    "status": "success",
                    "message": f"Test score updated to '{test_score}'.",
                    "test_score": test_score,
                    "data": dict(updated_row) if updated_row else {}
                })
            except Exception as e:
                print(f"[ERROR] Update test score error: {e}")
                self._send_json(500, {"status": "error", "message": f"Database error: {str(e)}"})
            return

        # 14. API: Host Dispatch Professional Shortlist Emails (Manual selection or batch)
        if path == "/api/admin/send-shortlist-emails":
            auth_header = self.headers.get("Authorization", "")
            if not is_valid_token(auth_header):
                self._send_json(401, {"status": "error", "message": "Unauthorized. Host access only."})
                return

            usns = [str(u).strip().upper() for u in body.get("usns", []) if str(u).strip()]
            ids = [int(i) for i in body.get("ids", []) if str(i).isdigit()]
            all_shortlisted = body.get("all_shortlisted", False)

            conn = get_db_connection()
            cursor = conn.cursor()

            if all_shortlisted:
                cursor.execute("SELECT * FROM registrations WHERE is_shortlisted = 1")
            elif usns:
                placeholders = ",".join("?" for _ in usns)
                cursor.execute(f"SELECT * FROM registrations WHERE UPPER(usn) IN ({placeholders})", usns)
            elif ids:
                placeholders = ",".join("?" for _ in ids)
                cursor.execute(f"SELECT * FROM registrations WHERE id IN ({placeholders})", ids)
            else:
                conn.close()
                self._send_json(400, {"status": "error", "message": "No candidates selected to receive shortlist emails."})
                return

            candidates = [dict(r) for r in cursor.fetchall()]
            conn.close()

            if not candidates:
                self._send_json(404, {"status": "error", "message": "No matching candidate records found for selected USNs/IDs."})
                return

            # Check SMTP configuration
            smtp_cfg = get_smtp_settings()
            is_enabled = smtp_cfg.get("smtp_enabled", "1") != "0"
            has_credentials = bool(smtp_cfg.get("smtp_user") and smtp_cfg.get("smtp_pass"))

            if not is_enabled or not has_credentials:
                self._send_json(400, {
                    "status": "error",
                    "message": "SMTP credentials are not configured in Host Portal. Please open Email Settings (in toolbar) to configure your Gmail/SMTP App Password first."
                })
                return

            # Dispatch in background thread
            dispatch_shortlist_emails_batch(candidates)

            self._send_json(200, {
                "status": "success",
                "message": f"Interview shortlist email dispatch initiated for {len(candidates)} candidate(s).",
                "count": len(candidates),
                "candidates": [{"name": c["name"], "usn": c["usn"], "email": c["email"]} for c in candidates]
            })
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
