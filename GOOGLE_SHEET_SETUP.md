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
function doGet(e) {
  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = ss.getActiveSheet();
    var p = (e && e.parameter) ? e.parameter : {};
    
    // 1. LIVE STATUS UPDATE via GET (High CORS compatibility across all mobile & desktop devices)
    if (p.action === "update_status" || p.action === "toggle_verify") {
      var result = updateCandidateStatus(sheet, p.usn, p.code, p.status);
      return ContentService
        .createTextOutput(JSON.stringify(result))
        .setMimeType(ContentService.MimeType.JSON);
    }
    
    // 2. DELETE CANDIDATE via GET
    if (p.action === "delete_candidate") {
      var delResult = deleteCandidateRow(sheet, p.usn, p.code);
      return ContentService
        .createTextOutput(JSON.stringify(delResult))
        .setMimeType(ContentService.MimeType.JSON);
    }
    
    // 3. DEFAULT: Return all applicant rows for live multi-device sync
    var data = sheet.getDataRange().getValues();
    if (!data || data.length < 2) {
      return ContentService
        .createTextOutput(JSON.stringify({ status: "success", count: 0, data: [] }))
        .setMimeType(ContentService.MimeType.JSON);
    }
    
    var rows = [];
    for (var i = 1; i < data.length; i++) {
      var row = data[i];
      if (!row[1] && !row[2]) continue; // Skip blank rows
      
      var isVerified = (String(row[8] || "").toLowerCase() === "verified" || String(row[8] || "") === "1");
      
      rows.push({
        id: i,
        timestamp: row[0] ? String(row[0]) : "",
        name: row[1] ? String(row[1]).trim() : "",
        usn: row[2] ? String(row[2]).trim().toUpperCase() : "",
        verification_code: row[3] ? String(row[3]).trim() : "",
        year: row[4] ? String(row[4]).trim() : "",
        branch: row[5] ? String(row[5]).trim() : "",
        email: row[6] ? String(row[6]).trim() : "",
        phone: row[7] ? String(row[7]).trim() : "",
        is_verified: isVerified ? 1 : 0,
        email_sent: 1
      });
    }
    
    return ContentService
      .createTextOutput(JSON.stringify({ status: "success", count: rows.length, data: rows }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ status: "error", message: err.toString() }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

function doPost(e) {
  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = ss.getActiveSheet();
    var p = (e && e.parameter) ? e.parameter : {};
    
    // Fallback if payload was delivered via JSON
    if (e && e.postData && e.postData.contents) {
      try {
        var parsed = JSON.parse(e.postData.contents);
        for (var key in parsed) { p[key] = parsed[key]; }
      } catch(parseErr) {}
    }
    
    // 1. STATUS UPDATE via POST
    if (p.action === "update_status" || p.action === "toggle_verify") {
      var result = updateCandidateStatus(sheet, p.usn, p.code, p.status);
      return ContentService
        .createTextOutput(JSON.stringify(result))
        .setMimeType(ContentService.MimeType.JSON);
    }
    
    // 2. DELETE CANDIDATE via POST
    if (p.action === "delete_candidate") {
      var delResult = deleteCandidateRow(sheet, p.usn, p.code);
      return ContentService
        .createTextOutput(JSON.stringify(delResult))
        .setMimeType(ContentService.MimeType.JSON);
    }
    
    // 3. NEW REGISTRATION SUBMISSION (from recruitment.html)
    var timestamp = p.timestamp || new Date().toLocaleString("en-IN", { timeZone: "Asia/Kolkata" });
    var name = p.name || "Applicant";
    var usn = (p.usn || "").toUpperCase();
    var year = p.year || "";
    var branch = p.branch || "";
    var email = (p.email || "").trim();
    var phone = p.phone || "";
    var verificationCode = p.verification_code || ("RC26-" + Math.random().toString(36).substring(2, 6).toUpperCase());
    var status = p.status || "Pending";
    
    if (!name && !usn) {
      return ContentService
        .createTextOutput(JSON.stringify({ status: "ignored", message: "Empty submission" }))
        .setMimeType(ContentService.MimeType.JSON);
    }
    
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

/**
 * Update candidate status in Google Sheet (Column 9 / Column I)
 */
function updateCandidateStatus(sheet, usn, code, status) {
  var data = sheet.getDataRange().getValues();
  var targetUsn = (usn || "").toString().trim().toUpperCase();
  var targetCode = (code || "").toString().trim().toUpperCase();
  
  var isV = (status === true || status === 1 || String(status).toLowerCase() === "verified" || String(status) === "1");
  var statusText = isV ? "Verified" : "Pending";
  
  if (!targetUsn && !targetCode) {
    return { status: "error", message: "Missing USN and verification code" };
  }
  
  var updatedCount = 0;
  for (var i = 1; i < data.length; i++) {
    var rowUsn = data[i][2] ? String(data[i][2]).trim().toUpperCase() : "";
    var rowCode = data[i][3] ? String(data[i][3]).trim().toUpperCase() : "";
    
    if ((targetUsn && rowUsn === targetUsn) || (targetCode && rowCode === targetCode)) {
      // Column 9 (1-indexed) is Column I (Status)
      sheet.getRange(i + 1, 9).setValue(statusText);
      updatedCount++;
    }
  }
  
  if (updatedCount > 0) {
    return { 
      status: "success", 
      message: "Applicant status updated to " + statusText,
      usn: targetUsn,
      is_verified: isV ? 1 : 0,
      updated_rows: updatedCount 
    };
  } else {
    return { 
      status: "not_found", 
      message: "No applicant found matching USN " + targetUsn + " or code " + targetCode 
    };
  }
}

/**
 * Delete candidate row from Google Sheet
 */
function deleteCandidateRow(sheet, usn, code) {
  var data = sheet.getDataRange().getValues();
  var targetUsn = (usn || "").toString().trim().toUpperCase();
  var targetCode = (code || "").toString().trim().toUpperCase();
  
  for (var i = data.length - 1; i >= 1; i--) {
    var rowUsn = data[i][2] ? String(data[i][2]).trim().toUpperCase() : "";
    var rowCode = data[i][3] ? String(data[i][3]).trim().toUpperCase() : "";
    
    if ((targetUsn && rowUsn === targetUsn) || (targetCode && rowCode === targetCode)) {
      sheet.deleteRow(i + 1);
      return { status: "success", message: "Applicant row removed from Google Sheet" };
    }
  }
  return { status: "not_found", message: "Applicant not found in sheet" };
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

> [!TIP]
> **If you already deployed earlier**:
> You don't need a new URL! Just click **Deploy** > **Manage deployments** > click the **Edit (pencil)** icon > under **Version** choose **New version** > click **Deploy**! The existing URL will instantly start serving live registrations!

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
