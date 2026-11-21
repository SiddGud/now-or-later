// Backend for the "Now or Later?" app.
// Paste into the Apps Script of a Google Sheet (Extensions -> Apps Script), then Deploy -> New deployment -> Web app.
// Every response becomes one row in the "responses" tab. New fields get new columns automatically.

function doPost(e) {
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var data = JSON.parse(e.postData.contents);
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = ss.getSheetByName('responses');
    if (!sheet) {
      sheet = ss.insertSheet('responses');
    }

    // Server time of arrival
    data.receivedAt = new Date().toISOString();

    // Read existing header, or start one
    var headers = [];
    if (sheet.getLastRow() > 0) {
      headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
    }

    // Add any new keys as new columns
    var keys = Object.keys(data);
    var added = false;
    for (var i = 0; i < keys.length; i++) {
      if (headers.indexOf(keys[i]) === -1) {
        headers.push(keys[i]);
        added = true;
      }
    }
    if (added) {
      sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
    }

    // Build the row in header order
    var row = [];
    for (var j = 0; j < headers.length; j++) {
      var v = data[headers[j]];
      if (v === undefined || v === null) {
        row.push('');
      } else {
        row.push(v);
      }
    }
    sheet.appendRow(row);

    return ContentService.createTextOutput('ok');
  } finally {
    lock.releaseLock();
  }
}

// Lets you check the deployment in a browser
function doGet() {
  return ContentService.createTextOutput('Backend is running.');
}
