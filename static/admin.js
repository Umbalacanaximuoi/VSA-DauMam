let adminToken = localStorage.getItem("vsa_admin_token");
let allLicenses = [];

document.addEventListener("DOMContentLoaded", () => {
    if (adminToken) {
        showDashboard();
        loadLicenses();
    } else {
        showLoginModal();
    }
});

function showLoginModal() {
    const loginEl = document.getElementById("adminLoginModal");
    const dashEl = document.getElementById("adminMainDashboard");
    if (loginEl) {
        loginEl.classList.remove("hidden");
        loginEl.style.display = "flex";
    }
    if (dashEl) {
        dashEl.classList.add("hidden");
        dashEl.style.display = "none";
    }
}

function showDashboard() {
    const loginEl = document.getElementById("adminLoginModal");
    const dashEl = document.getElementById("adminMainDashboard");
    if (loginEl) {
        loginEl.classList.add("hidden");
        loginEl.style.display = "none";
    }
    if (dashEl) {
        dashEl.classList.remove("hidden");
        dashEl.style.display = "block";
    }
}

async function submitAdminLogin() {
    const pwd = document.getElementById("adminPasswordInput").value.trim();
    const errEl = document.getElementById("loginErrorMsg");
    errEl.classList.add("hidden");
    
    if (!pwd) {
        errEl.innerText = "Vui lòng nhập mật khẩu quản trị!";
        errEl.classList.remove("hidden");
        return;
    }
    
    try {
        const res = await fetch("/api/admin/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ password: pwd })
        });
        
        const data = await res.json();
        if (res.ok && data.token) {
            adminToken = data.token;
            localStorage.setItem("vsa_admin_token", adminToken);
            showDashboard();
            loadLicenses();
        } else {
            errEl.innerText = data.detail || "Mật khẩu quản trị không chính xác!";
            errEl.classList.remove("hidden");
        }
    } catch (e) {
        errEl.innerText = "Lỗi kết nối máy chủ: " + e;
        errEl.classList.remove("hidden");
    }
}

function adminLogout() {
    localStorage.removeItem("vsa_admin_token");
    adminToken = null;
    showLoginModal();
}

function openAppAsAdmin() {
    const token = adminToken || localStorage.getItem("vsa_admin_token") || "";
    window.open(`/?token=${encodeURIComponent(token)}`, '_blank');
}

async function loadLicenses() {
    try {
        const res = await fetch("/api/admin/licenses", {
            headers: { "Authorization": `Bearer ${adminToken}` }
        });
        
        if (res.status === 401) {
            adminLogout();
            return;
        }
        
        const resJson = await res.json();
        if (resJson.status === "success") {
            allLicenses = resJson.licenses || [];
            updateStats(resJson.stats);
            renderLicensesTable(allLicenses);
        }
    } catch (e) {
        console.error("Lỗi tải danh sách:", e);
    }
}

function updateStats(stats) {
    if (!stats) return;
    document.getElementById("statTotal").innerText = stats.total;
    document.getElementById("statActive").innerText = stats.active;
    document.getElementById("statExpiring").innerText = stats.expiring_soon;
    document.getElementById("statExpired").innerText = (stats.expired || 0) + (stats.revoked || 0);
}

function filterLicensesTable() {
    const query = document.getElementById("adminSearchInput").value.trim().toUpperCase();
    const statusFilter = document.getElementById("adminFilterStatus").value;
    
    let filtered = allLicenses;
    
    if (statusFilter === "ACTIVE") {
        filtered = filtered.filter(l => l.status === "ACTIVE" && l.days_left > 7);
    } else if (statusFilter === "EXPIRING") {
        filtered = filtered.filter(l => l.status === "ACTIVE" && l.days_left <= 7);
    } else if (statusFilter === "EXPIRED") {
        filtered = filtered.filter(l => l.status === "EXPIRED");
    } else if (statusFilter === "REVOKED") {
        filtered = filtered.filter(l => l.status === "REVOKED");
    }
    
    if (query) {
        filtered = filtered.filter(l => 
            l.client.toUpperCase().includes(query) ||
            l.license_key.toUpperCase().includes(query) ||
            l.bound_hwid.toUpperCase().includes(query)
        );
    }
    
    renderLicensesTable(filtered);
}

function renderLicensesTable(list) {
    const tbody = document.getElementById("licensesTableBody");
    if (!list || list.length === 0) {
        tbody.innerHTML = `<tr><td colspan="10" style="text-align:center; padding:30px; color:#8A9BA8;">Không tìm thấy khách hàng nào.</td></tr>`;
        return;
    }
    
    let html = '';
    list.forEach((lic, idx) => {
        let statusBadge = '';
        if (lic.status === "REVOKED") {
            statusBadge = `<span class="status-pill pill-danger">⛔ Bị Khóa</span>`;
        } else if (lic.status === "EXPIRED") {
            statusBadge = `<span class="status-pill pill-danger">🔴 Hết Hạn</span>`;
        } else if (lic.days_left <= 7) {
            statusBadge = `<span class="status-pill pill-warning">🟡 Còn ${lic.days_left} ngày</span>`;
        } else {
            statusBadge = `<span class="status-pill pill-success">🟢 Active (${lic.days_left}d)</span>`;
        }
        
        const isRevoked = lic.status === "REVOKED";
        const revokeBtnText = isRevoked ? "🔓 Mở Khóa" : "⛔ Khóa Key";
        const revokeBtnClass = isRevoked ? "btn-success-sm" : "btn-warning-sm";
        
        html += `
            <tr>
                <td>${idx + 1}</td>
                <td><strong>${lic.client}</strong></td>
                <td><span class="plan-tag">${lic.plan}</span></td>
                <td>
                    <div class="key-cell">
                        <code>${lic.license_key.substring(0, 16)}...</code>
                        <button class="btn-copy-sm" onclick="copyText('${lic.license_key}')">Copy</button>
                    </div>
                </td>
                <td><code>${lic.bound_hwid}</code></td>
                <td><small>${lic.created_at}</small></td>
                <td><small>${lic.expires_at}</small></td>
                <td><strong>${lic.days_left} ngày</strong></td>
                <td>${statusBadge}</td>
                <td>
                    <div class="table-actions">
                        <button class="btn-primary-sm" onclick="quickRenew('${lic.license_key}', 30)">+30 Ngày</button>
                        <button class="${revokeBtnClass}" onclick="toggleRevoke('${lic.license_key}', '${lic.status}')">${revokeBtnText}</button>
                        <button class="btn-danger-sm" onclick="deleteLicense('${lic.license_key}', '${lic.client}')">Xóa</button>
                    </div>
                </td>
            </tr>
        `;
    });
    
    tbody.innerHTML = html;
}

function copyText(text) {
    navigator.clipboard.writeText(text);
    alert("Đã sao chép: " + text);
}

// ==================== CREATE LICENSE ====================
function openCreateModal() {
    document.getElementById("createLicenseModal").classList.remove("hidden");
}

function closeCreateModal() {
    document.getElementById("createLicenseModal").classList.add("hidden");
}

function toggleCustomDays(val) {
    const grp = document.getElementById("customDaysGroup");
    if (val === "custom") grp.classList.remove("hidden");
    else grp.classList.add("hidden");
}

async function submitCreateLicense() {
    const client = document.getElementById("newClientName").value.trim();
    if (!client) { alert("Vui lòng nhập tên khách hàng!"); return; }
    
    let daysVal = document.getElementById("newDaysSelect").value;
    let days = parseInt(daysVal);
    if (daysVal === "custom") {
        days = parseInt(document.getElementById("newCustomDays").value) || 30;
    }
    
    const hwid = document.getElementById("newBoundHwid").value.trim() || "ANY";
    const plan = document.getElementById("newPlanName").value.trim() || "VIP";
    const notes = document.getElementById("newNotes").value.trim();
    
    try {
        const res = await fetch("/api/admin/licenses/create", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${adminToken}`
            },
            body: JSON.stringify({
                client_name: client,
                days: days,
                bound_hwid: hwid,
                plan_name: plan,
                notes: notes
            })
        });
        
        const data = await res.json();
        if (res.ok && data.success) {
            alert(`🎉 TẠO KEY THÀNH CÔNG!\nKhách hàng: ${data.client}\nMã Key: ${data.license_key}\nHạn dùng: ${data.expires_at}`);
            closeCreateModal();
            loadLicenses();
        } else {
            alert("Lỗi: " + (data.detail || data.message));
        }
    } catch (e) {
        alert("Lỗi kết nối: " + e);
    }
}

// ==================== RENEW & REVOKE ====================
async function quickRenew(key, days) {
    if (!confirm(`Bạn có chắc chắn muốn gia hạn thêm ${days} ngày cho License Key này?`)) return;
    
    try {
        const res = await fetch("/api/admin/licenses/renew", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${adminToken}`
            },
            body: JSON.stringify({ license_key: key, extra_days: days })
        });
        const data = await res.json();
        if (res.ok && data.success) {
            alert(`🎉 GIA HẠN THÀNH CÔNG!\nHạn dùng mới: ${data.new_expires_at}`);
            loadLicenses();
        } else {
            alert("Lỗi: " + (data.detail || data.message));
        }
    } catch (e) {
        alert("Lỗi kết nối: " + e);
    }
}

async function toggleRevoke(key, currentStatus) {
    const isRevoking = currentStatus !== "REVOKED";
    const confirmMsg = isRevoking 
        ? "⚠️ BẠN CÓ CHẮC MUỐN KHÓA BẢN QUYỀN NÀY?\nMáy khách sẽ lập tức bị chặn trong vòng 5 giây."
        : "Mở khóa bản quyền cho khách hàng này?";
    if (!confirm(confirmMsg)) return;
    
    const endpoint = isRevoking ? "/api/admin/licenses/revoke" : "/api/admin/licenses/unrevoke";
    try {
        const res = await fetch(endpoint, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${adminToken}`
            },
            body: JSON.stringify({ license_key: key })
        });
        const data = await res.json();
        if (res.ok && data.success) {
            alert(data.message);
            loadLicenses();
        } else {
            alert("Lỗi: " + (data.detail || data.message));
        }
    } catch (e) {
        alert("Lỗi kết nối: " + e);
    }
}

async function deleteLicense(key, client) {
    if (!confirm(`⚠️ CẢNH BÁO: Bạn có chắc muốn XÓA vĩnh viễn khách hàng [${client}] khỏi hệ thống?`)) return;
    
    try {
        const res = await fetch("/api/admin/licenses/delete", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${adminToken}`
            },
            body: JSON.stringify({ license_key: key })
        });
        const data = await res.json();
        if (res.ok && data.success) {
            alert(data.message);
            loadLicenses();
        } else {
            alert("Lỗi: " + (data.detail || data.message));
        }
    } catch (e) {
        alert("Lỗi kết nối: " + e);
    }
}

// ==================== WARNINGS ====================
async function openWarningModal() {
    const modal = document.getElementById("warningModal");
    modal.classList.remove("hidden");
    const container = document.getElementById("warningListContainer");
    container.innerHTML = `<p style="color:#8A9BA8;">Đang kiểm tra danh sách sắp hết hạn...</p>`;
    
    try {
        const res = await fetch("/api/admin/warnings?days=7", {
            headers: { "Authorization": `Bearer ${adminToken}` }
        });
        const data = await res.json();
        
        if (data.count === 0) {
            container.innerHTML = `
                <div style="padding:20px; text-align:center; color:#10B981; font-size:14px;">
                    ✅ Tuyệt vời! Không có khách hàng nào sắp hết hạn trong 7 ngày tới.
                </div>
            `;
            return;
        }
        
        let html = `<p style="margin-bottom:14px; color:#F59E0B; font-weight:700;">🔔 Phát hiện ${data.count} khách hàng cần chăm sóc & nhắc gia hạn:</p>`;
        data.clients.forEach(c => {
            html += `
                <div class="warning-item-box">
                    <div class="warning-item-header">
                        <strong>${c.client}</strong> — <span style="color:#F59E0B; font-weight:700;">Còn ${c.days_left} ngày (Hết hạn: ${c.expires_at})</span>
                    </div>
                    <textarea class="warning-template-textarea" readonly rows="4">${c.message_template}</textarea>
                    <button class="btn-copy-sm" style="margin-top:6px;" onclick="copyText(\`${c.message_template}\`)">📋 Sao chép mẫu tin nhắn Zalo</button>
                </div>
            `;
        });
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = `<p style="color:#EF4444;">Lỗi: ${e}</p>`;
    }
}

function closeWarningModal() {
    document.getElementById("warningModal").classList.add("hidden");
}
