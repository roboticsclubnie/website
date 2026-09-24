# Google Sheet (Live Cloud Sync & Automated Email Setup Guide)

This guide explains how to connect your **Robotics Club NIE Recruitment 2026** portal to a live Google Sheet that also **automatically sends confirmation emails with unique verification codes** directly from your club's Google account!

---

## ⚡ 3-Minute Setup Instructions

### Step 1: Create a Google Sheet
1. Open [Google Sheets](https://sheets.new) in your browser.
2. Name the spreadsheet: **`Robotics Club NIE — Recruitment 2026`**.
3. In row 1, set up the column headers:
   - **A1**: `Timestamp`
   - **B1**: `Full Name`
   - **C1**: `USN`
   - **D1**: `Verification Code`
   - **E1**: `Year of Study`
   - **F1**: `Branch`
   - **G1**: `Email ID`
   - **H1**: `Phone Number`
   - **I1**: `Status`

---

### Step 2: Add the Google Apps Script
1. In the Google Sheet top menu, click **Extensions** > **Apps Script**.
2. Delete any existing code in the editor, and paste the following script:

```javascript
function doPost(e) {
  try {
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
    var p = e.parameter;
    
    // Extract parameters from form submission
    var timestamp = p.timestamp || new Date().toLocaleString("en-IN", { timeZone: "Asia/Kolkata" });
    var name = p.name || "Applicant";
    var usn = (p.usn || "").toUpperCase();
    var year = p.year || "";
    var branch = p.branch || "";
    var email = p.email || "";
    var phone = p.phone || "";
    
    // Use submitted verification code or generate a unique one
    var verificationCode = p.verification_code || ("RC26-" + Math.random().toString(36).substring(2, 6).toUpperCase());
    var status = "Pending";
    
    // Append the row to your spreadsheet
    sheet.appendRow([timestamp, name, usn, verificationCode, year, branch, email, phone, status]);
    
    // Automatically send official confirmation email if email is provided
    if (email && email.indexOf("@") !== -1) {
      try {
        var subject = "Registration Confirmed: Recruitment 2026 — Robotics Club NIE [Code: " + verificationCode + "]";
        
        var htmlBody = 
          '<div style="font-family: Arial, sans-serif; background: #000814; color: #f1f5f9; padding: 30px; border-radius: 12px; max-width: 600px; margin: auto;">' +
            '<div style="text-align: center; border-bottom: 2px solid #00eaff; padding-bottom: 15px; margin-bottom: 20px;">' +
              '<h2 style="color: #ffffff; margin: 0; letter-spacing: 1px;">THE ROBOTICS CLUB</h2>' +
              '<p style="color: #00eaff; font-size: 13px; margin: 4px 0 0 0;">The National Institute of Engineering, Mysuru</p>' +
            '</div>' +
            '<p>Dear <strong>' + name + '</strong>,</p>' +
            '<p>Thank you for registering for the 2026 Recruitment Drive at The Robotics Club, NIE Mysuru!</p>' +
            '<div style="background: #001b3a; border: 2px dashed #00eaff; border-radius: 10px; padding: 20px; text-align: center; margin: 25px 0;">' +
              '<div style="font-size: 11px; text-transform: uppercase; color: #00eaff; letter-spacing: 2px; font-weight: bold;">Your Verification Code</div>' +
              '<div style="font-size: 32px; font-weight: bold; letter-spacing: 5px; color: #ffffff; padding: 8px 0; font-family: monospace;">' + verificationCode + '</div>' +
              '<div style="font-size: 12px; color: #94a3b8;">Present this code during orientation & interview rounds.</div>' +
            '</div>' +
            '<table style="width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 13px; color: #cbd5e1;">' +
              '<tr><td style="padding: 6px 0; color: #64748b;">USN:</td><td style="font-weight: bold; color: #ffffff;">' + usn + '</td></tr>' +
              '<tr><td style="padding: 6px 0; color: #64748b;">Year & Branch:</td><td style="color: #ffffff;">' + year + ' — ' + branch + '</td></tr>' +
              '<tr><td style="padding: 6px 0; color: #64748b;">Phone:</td><td style="color: #ffffff;">' + phone + '</td></tr>' +
            '</table>' +
            '<p style="font-size: 12px; color: #94a3b8; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 15px;">' +
              'For queries: <a href="mailto:roboticsclubnie@nie.ac.in" style="color: #00eaff;">roboticsclubnie@nie.ac.in</a> | Instagram: @roboticsclub_nie' +
            '</p>' +
          '</div>';

        MailApp.sendEmail({
          to: email,
          subject: subject,
          htmlBody: htmlBody,
          name: "Robotics Club NIE"
        });
      } catch (mailErr) {
        Logger.log("Mail delivery notice: " + mailErr);
      }
    }
    
    return ContentService
      .createTextOutput(JSON.stringify({ 
        status: "success", 
        message: "Registration recorded successfully", 
        verification_code: verificationCode 
      }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (error) {
    return ContentService
      .createTextOutput(JSON.stringify({ status: "error", error: error.toString() }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}
```

3. Click the **Save** (disk) icon or press `Ctrl + S`.

---

### Step 3: Deploy as Web App
1. Click the blue **Deploy** button (top right) > **New deployment**.
2. Click the gear icon next to "Select type" and select **Web app**.
3. Set the configuration:
   - **Description**: `Recruitment 2026 Confirmation Webhook`
   - **Execute as**: `Me (your email)`
   - **Who has access**: **`Anyone`** *(Important: Must be 'Anyone' so student submissions from the website can be recorded)*
4. Click **Deploy**.
5. Grant permissions if prompted (Click *Advanced* > *Go to Untitled project (unsafe)* > *Allow*).
6. Copy the **Web App URL** (e.g. `https://script.google.com/macros/s/AKfycb.../exec`).

---

### Step 4: Paste the URL in `recruitment.js`
Open `recruitment.js` and set:

```javascript
const GOOGLE_SHEET_SCRIPT_URL = "YOUR_COPIED_WEB_APP_URL_HERE";
```

Save the file. **Done!**

---

## 🔒 Verification & Host Admin Features
- When running locally or on a server with `python server.py`, you can log into **Host Portal** (`http://localhost:8080/admin.html`) using passcode `roboticsnie2026`.
- Features in Host Portal:
  - **🛡️ Verify Code**: Type or scan an applicant's code (e.g. `RC26-8K4F`) to view their registration and check them in.
  - **📧 Email Settings**: Configure your SMTP/Gmail App Password with 1-click test email sending.
  - **📊 Live Excel Export**: Download real-time `.xlsx` spreadsheets with verification codes and check-in statuses.
