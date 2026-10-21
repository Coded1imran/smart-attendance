/**
 * Main Attendance Workflow Manager (AttendAI)
 */

// Helper to display alert/toast messages
function showNotification(message, type = "info") {
  const existing = document.getElementById("toast-banner");
  if (existing) existing.remove();

  const toast = document.createElement("div");
  toast.id = "toast-banner";
  toast.style.position = "fixed";
  toast.style.top = "20px";
  toast.style.right = "20px";
  toast.style.padding = "14px 20px";
  toast.style.borderRadius = "8px";
  toast.style.color = "#fff";
  toast.style.fontWeight = "600";
  toast.style.fontSize = "0.9rem";
  toast.style.zIndex = "99999";
  toast.style.boxShadow = "0 10px 15px -3px rgba(0,0,0,0.1)";

  if (type === "success") toast.style.background = "#10b981";
  else if (type === "error") toast.style.background = "#ef4444";
  else toast.style.background = "#4f46e5";

  toast.textContent = message;
  document.body.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transition = "opacity 0.5s ease";
    setTimeout(() => toast.remove(), 500);
  }, 4000);
}

// ----------------- Lecturer Live Attendance Refresh ----------------- //

function initLecturerLiveFeed(sessionId) {
  const tableBody = document.getElementById("live-attendance-tbody");
  const codeDigits = document.getElementById("live-code-digits");
  const codeTimer = document.getElementById("live-code-timer");

  async function updateCode() {
    try {
      const res = await fetch(`/lecturer/api/sessions/${sessionId}/code`);
      if (res.ok) {
        const data = await res.json();
        if (codeDigits) codeDigits.textContent = data.rotating_code;
        if (codeTimer) codeTimer.textContent = `Expires in ${data.seconds_remaining}s`;
      }
    } catch (e) {
      console.warn("Could not sync rotating code", e);
    }
  }

  async function updateTable() {
    try {
      const res = await fetch(`/lecturer/api/sessions/${sessionId}/records`);
      if (!res.ok) return;
      const data = await res.json();

      if (!tableBody) return;
      if (data.records.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:32px; color:#64748b;">No attendance recorded yet. Students will appear here in real time.</td></tr>`;
        return;
      }

      tableBody.innerHTML = data.records.map(r => `
        <tr>
          <td><strong>${r.student_name}</strong></td>
          <td>${r.matric_no}</td>
          <td>${r.date} ${r.time}</td>
          <td>
            <span class="badge ${r.status === 'Present' ? 'badge-present' : (r.status === 'Pending Review' ? 'badge-pending' : 'badge-rejected')}">
              ${r.status}
            </span>
          </td>
          <td><strong>${r.verification_score}%</strong></td>
          <td>
            ${r.flagged ? '<span style="color:#ef4444; font-weight:bold; font-size:1.1rem;" title="' + (r.flag_reason || 'Flagged') + '">⚠️</span>' : '<span style="color:#10b981;">✓</span>'}
          </td>
          <td>
            ${r.flagged || r.status === 'Pending Review' ? `
              <button class="btn btn-sm btn-success" onclick="reviewRecord(${r.id}, 'Present')">Approve</button>
              <button class="btn btn-sm btn-danger" onclick="reviewRecord(${r.id}, 'Rejected')">Reject</button>
            ` : '<span style="color:#94a3b8; font-size:0.8rem;">Completed</span>'}
          </td>
        </tr>
      `).join("");
    } catch (e) {
      console.warn("Live table poll error", e);
    }
  }

  // Initial calls
  updateCode();
  updateTable();

  // 1-second interval for rotating code clock
  setInterval(updateCode, 1000);
  // 5-second interval for real-time live attendance feed
  setInterval(updateTable, 5000);
}

// ----------------- Review Modal Action ----------------- //

async function reviewRecord(recordId, newStatus) {
  try {
    const res = await fetch(`/lecturer/api/records/${recordId}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: newStatus })
    });
    const result = await res.json();
    if (res.ok) {
      showNotification(`Record ${recordId} updated to ${newStatus}.`, "success");
      // Trigger instant table reload
      const evt = new CustomEvent("attendanceUpdated");
      window.dispatchEvent(evt);
    } else {
      showNotification(result.detail || "Error reviewing record.", "error");
    }
  } catch (err) {
    showNotification("Network error reviewing record.", "error");
  }
}
