let currentLicense = null;
let currentScanData = { tier1_cuoc: [], tier2_pocket: [], tier3_pivot: [] };
let activeScanTier = 'all';

function getAuthHeaders() {
    const headers = { "Content-Type": "application/json" };
    const adminToken = localStorage.getItem("vsa_admin_token");
    if (adminToken) {
        headers["Authorization"] = `Bearer ${adminToken}`;
    }
    return headers;
}

document.addEventListener("DOMContentLoaded", () => {
    initHwid();
    checkLicenseStatus();
    // Heartbeat check every 3 minutes for remote revocation/renewal sync
    setInterval(checkLicenseStatus, 180000);
});

async function initHwid() {
    try {
        const res = await fetch("/api/license/hwid");
        const data = await res.json();
        if (data.hwid) {
            const el = document.getElementById("gatekeeperHwidText");
            if (el) el.innerText = data.hwid;
            const modalEl = document.getElementById("modalHwidText");
            if (modalEl) modalEl.innerText = data.hwid;
            const codeEl = document.getElementById("gatekeeperTransferCode");
            if (codeEl) codeEl.innerText = `KICHHOAT ${data.hwid}`;
            const qrImg = document.getElementById("gatekeeperQrImg");
            if (qrImg) {
                const addInfo = encodeURIComponent(`KICHHOAT ${data.hwid}`);
                qrImg.src = `https://api.vietqr.io/image/970422-0988888888-compact2.jpg?amount=399000&addInfo=${addInfo}`;
            }
        }
    } catch (e) {
        console.error("Lỗi lấy HWID:", e);
    }
}

async function checkLicenseStatus() {
    try {
        const urlParams = new URLSearchParams(window.location.search);
        const queryToken = urlParams.get("token") || urlParams.get("admin_token");
        if (queryToken) {
            localStorage.setItem("vsa_admin_token", queryToken);
        }
        
        const headers = {};
        const adminToken = localStorage.getItem("vsa_admin_token");
        if (adminToken) {
            headers["Authorization"] = `Bearer ${adminToken}`;
        }
        
        const res = await fetch("/api/license/status", { headers: headers });
        const data = await res.json();
        currentLicense = data;
        
        const gatekeeper = document.getElementById("authGatekeeper");
        const mainApp = document.getElementById("mainAppContainer");
        const badge = document.getElementById("licenseBadge");
        const badgeText = document.getElementById("licenseBadgeText");
        
        if (data.valid) {
            // UNLOCKED: Hide gatekeeper, show main app
            document.body.classList.remove("locked");
            if (gatekeeper) {
                gatekeeper.classList.add("hidden");
                gatekeeper.style.display = "none";
            }
            if (mainApp) {
                mainApp.classList.remove("hidden");
                mainApp.style.display = "block";
            }
            
            if (badge) {
                badge.className = "license-badge active";
                if (data.is_admin) {
                    if (badgeText) badgeText.innerText = `👑 Quản Trị Viên (Toàn Quyền)`;
                } else {
                    if (badgeText) badgeText.innerText = `🟢 Gói ${data.plan || 'VIP'}: Còn ${data.days_left} ngày (${data.client})`;
                }
            }
            
            document.getElementById("expiredModal")?.classList.add("hidden");
            evaluateStock();
        } else {
            // LOCKED: Show gatekeeper, hide main app
            document.body.classList.add("locked");
            if (mainApp) {
                mainApp.classList.add("hidden");
                mainApp.style.display = "none";
            }
            if (gatekeeper) {
                gatekeeper.classList.remove("hidden");
                gatekeeper.style.display = "flex";
            }
            
            const banner = document.getElementById("gatekeeperStatusBanner");
            const msgEl = document.getElementById("gatekeeperStatusMsg");
            
            if (data.status === "REVOKED") {
                if (badge) badge.className = "license-badge expired";
                if (badgeText) badgeText.innerText = `⛔ Bị Khóa Bản Quyền`;
                if (banner) banner.className = "gatekeeper-status-banner banner-danger";
                if (msgEl) msgEl.innerText = "⛔ BẢN QUYỀN CỦA BẠN ĐÃ BỊ KHÓA TỪ MÁY CHỦ. Vui lòng liên hệ Admin để mở lại.";
            } else if (data.status === "EXPIRED") {
                if (badge) badge.className = "license-badge expired";
                if (badgeText) badgeText.innerText = `🔴 Hết Hạn Bản Quyền`;
                if (banner) banner.className = "gatekeeper-status-banner banner-danger";
                if (msgEl) msgEl.innerText = `🔴 Bản quyền của bạn (${data.client || 'VIP'}) đã hết hạn vào ngày ${data.expired_at}. Vui lòng gia hạn.`;
                showExpiredModal(data);
            } else {
                if (badge) badge.className = "license-badge warning";
                if (badgeText) badgeText.innerText = `🟡 Chưa Kích Hoạt`;
                if (banner) banner.className = "gatekeeper-status-banner banner-warning";
                if (msgEl) msgEl.innerText = "⚠️ Phần mềm chưa kích hoạt. Vui lòng nhập License Key từ Admin để mở khóa.";
            }
        }
    } catch (e) {
        console.error("Lỗi kiểm tra bản quyền:", e);
    }
}

// ==================== GATEKEEPER ACTIONS ====================
function switchGatekeeperTab(tab) {
    const tabs = ['login', 'register', 'pricing'];
    tabs.forEach(t => {
        const btn = document.getElementById('gTab' + t.charAt(0).toUpperCase() + t.slice(1));
        const content = document.getElementById('tabContent' + t.charAt(0).toUpperCase() + t.slice(1));
        if (t === tab) {
            btn?.classList.add('active');
            if (content) {
                content.classList.remove('hidden');
                content.style.display = 'block';
            }
        } else {
            btn?.classList.remove('active');
            if (content) {
                content.classList.add('hidden');
                content.style.display = 'none';
            }
        }
    });
}

function copyGatekeeperHwid() {
    const hwid = document.getElementById("gatekeeperHwidText").innerText;
    navigator.clipboard.writeText(hwid);
    alert("📋 Đã sao chép Mã Máy (Hardware ID): " + hwid + "\nHãy gửi mã này qua Zalo cho Admin!");
}

function copyRegistrationInfo() {
    const name = document.getElementById("regNameInput").value.trim() || "Chưa nhập";
    const phone = document.getElementById("regPhoneInput").value.trim() || "Chưa nhập";
    const plan = document.getElementById("regPlanSelect").options[document.getElementById("regPlanSelect").selectedIndex].text;
    const hwid = document.getElementById("gatekeeperHwidText").innerText;
    
    const text = (
        `🌱 [ĐĂNG KÝ BẢN QUYỀN VSA ĐẬU MẦM PRO]\n` +
        `- Họ và tên: ${name}\n` +
        `- SĐT/Zalo: ${phone}\n` +
        `- Gói đăng ký: ${plan}\n` +
        `- Mã máy (HWID): ${hwid}\n` +
        `Admin cấp key giúp tôi nhé!`
    );
    
    navigator.clipboard.writeText(text);
    alert("📋 ĐÃ SAO CHÉP THÔNG TIN ĐĂNG KÝ!\n\nHãy mở Zalo và Dán (Paste) tin nhắn này gửi cho Admin (0988.888.888) để nhận key ngay nhé!");
}

async function submitGatekeeperActivation() {
    const key = document.getElementById("gatekeeperKeyInput").value.trim();
    if (!key) { alert("Vui lòng dán License Key vào ô trống!"); return; }
    
    try {
        const res = await fetch("/api/license/activate", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({license_key: key})
        });
        const data = await res.json();
        if (data.valid) {
            alert(`🎉 KÍCH HOẠT THÀNH CÔNG!\nChào mừng: ${data.client}\nGói: ${data.plan}\nHạn dùng còn: ${data.days_left} ngày.`);
            document.body.classList.remove("locked");
            const gatekeeper = document.getElementById("authGatekeeper");
            const mainApp = document.getElementById("mainAppContainer");
            if (gatekeeper) {
                gatekeeper.classList.add("hidden");
                gatekeeper.style.display = "none";
            }
            if (mainApp) {
                mainApp.classList.remove("hidden");
                mainApp.style.display = "block";
            }
            checkLicenseStatus();
        } else {
            alert(`❌ KÍCH HOẠT THẤT BẠI: ${data.message}`);
        }
    } catch (e) {
        alert("Lỗi kết nối máy chủ: " + e);
    }
}

// ==================== MODAL ACTIONS ====================
function openLicenseModal() { showLicenseModal(currentLicense); }
function closeLicenseModal() { document.getElementById("licenseModal").classList.add("hidden"); }

function showLicenseModal(lic) {
    const modal = document.getElementById("licenseModal");
    const hwidEl = document.getElementById("modalHwidText");
    const detailEl = document.getElementById("licenseStatusDetail");
    
    if (lic && lic.hwid) hwidEl.innerText = lic.hwid;
    
    if (lic && lic.valid) {
        detailEl.innerHTML = `
            <div style="background: rgba(16,185,129,0.1); border: 1px solid #10B981; padding: 12px; border-radius: 8px; margin-bottom: 12px; font-size: 13px;">
                ✅ <strong>Đang sử dụng:</strong> ${lic.client} (${lic.plan})<br>
                ⏳ <strong>Hạn dùng:</strong> Còn ${lic.days_left} ngày (Đến: ${lic.expired_at || 'Vĩnh Viễn'})
            </div>
            <button class="btn-danger-sm" style="width:100%; padding:8px; margin-bottom:14px; font-size:12px;" onclick="deactivateAndReset()">🔄 Thoát Bản Quyền Này (Để Thử Nghiệm Key Khác)</button>
        `;
    } else if (lic && lic.status === "REVOKED") {
        detailEl.innerHTML = `
            <div style="background: rgba(239,68,68,0.1); border: 1px solid #EF4444; padding: 10px; border-radius: 8px; margin-bottom: 12px; font-size: 13px; color: #EF4444;">
                ⛔ Bản quyền này đã bị KHÓA từ Quản trị viên.
            </div>
        `;
    } else if (lic && lic.status === "EXPIRED") {
        detailEl.innerHTML = `
            <div style="background: rgba(239,68,68,0.1); border: 1px solid #EF4444; padding: 10px; border-radius: 8px; margin-bottom: 12px; font-size: 13px; color: #EF4444;">
                ❌ Bản quyền của <strong>${lic.client || 'bạn'}</strong> đã hết hạn vào ngày <strong>${lic.expired_at}</strong>.
            </div>
        `;
    } else {
        detailEl.innerHTML = `
            <div style="background: rgba(245,158,11,0.1); border: 1px solid #F59E0B; padding: 10px; border-radius: 8px; margin-bottom: 12px; font-size: 13px; color: #F59E0B;">
                ⚠️ Chưa có bản quyền. Vui lòng nhập License Key từ Admin.
            </div>
        `;
    }
    modal.classList.remove("hidden");
}

async function deactivateAndReset() {
    if (!confirm("Bạn có chắc chắn muốn thoát bản quyền hiện tại để thử nghiệm tài khoản người dùng khác?")) return;
    
    try {
        localStorage.removeItem("vsa_admin_token");
        await fetch("/api/license/reset", { method: "POST" });
        closeLicenseModal();
        alert("Đã thoát bản quyền! Màn hình Khởi động sẽ mở ra để bạn dán License Key mới.");
        checkLicenseStatus();
    } catch (e) {
        alert("Lỗi: " + e);
    }
}

function showExpiredModal(lic) {
    const modal = document.getElementById("expiredModal");
    if (!modal) return;
    document.getElementById("expiredHwidText").innerText = lic?.hwid || "--";
    document.getElementById("transferContentText").innerText = `GIAHAN ${lic?.hwid || 'DAUMAM'}`;
    
    const qrImg = document.getElementById("vietQrImg");
    if (qrImg) {
        const addInfo = encodeURIComponent(`GIAHAN ${lic?.hwid || 'DAUMAM'}`);
        qrImg.src = `https://api.vietqr.io/image/970422-0988888888-compact2.jpg?amount=399000&addInfo=${addInfo}`;
    }
    modal.classList.remove("hidden");
}

function copyHwid() {
    const hwid = document.getElementById("modalHwidText").innerText;
    navigator.clipboard.writeText(hwid);
    alert("Đã sao chép Mã Máy (Hardware ID): " + hwid);
}

async function submitActivation() {
    const key = document.getElementById("licenseKeyInput").value.trim();
    if (!key) { alert("Vui lòng nhập License Key!"); return; }
    
    try {
        const res = await fetch("/api/license/activate", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({license_key: key})
        });
        const data = await res.json();
        if (data.valid) {
            alert(`🎉 KÍCH HOẠT THÀNH CÔNG!\nChào mừng: ${data.client}\nGói: ${data.plan}\nCòn lại: ${data.days_left} ngày.`);
            closeLicenseModal();
            checkLicenseStatus();
        } else {
            alert(`❌ KÍCH HOẠT THẤT BẠI: ${data.message}`);
        }
    } catch (e) {
        alert("Lỗi kết nối máy chủ: " + e);
    }
}

async function submitRenewal() {
    const key = document.getElementById("renewalKeyInput").value.trim();
    if (!key) { alert("Vui lòng nhập License Key mới!"); return; }
    
    try {
        const res = await fetch("/api/license/activate", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({license_key: key})
        });
        const data = await res.json();
        if (data.valid) {
            alert(`🎉 GIA HẠN THÀNH CÔNG!\nChào mừng bạn trở lại! Hạn dùng: Còn ${data.days_left} ngày.`);
            document.getElementById("expiredModal")?.classList.add("hidden");
            checkLicenseStatus();
        } else {
            alert(`❌ GIA HẠN THẤT BẠI: ${data.message}`);
        }
    } catch (e) {
        alert("Lỗi kết nối: " + e);
    }
}

function quickSearch(sym) {
    document.getElementById("symbolInput").value = sym;
    evaluateStock();
}

function formatMd(text) {
    if (!text) return '';
    return text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\n/g, '<br>');
}

// ==================== EVALUATE STOCK ====================
async function evaluateStock() {
    const sym = document.getElementById("symbolInput")?.value.trim().toUpperCase() || "TCB";
    const dateVal = document.getElementById("dateInput")?.value;
    
    const searchBtn = document.querySelector(".btn-search");
    if (searchBtn) searchBtn.innerText = "⏳ Đang chẩn đoán...";
    
    try {
        const res = await fetch("/api/evaluate", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({symbol: sym, target_date: dateVal || null})
        });
        
        if (res.status === 403) {
            const errData = await res.json();
            checkLicenseStatus();
            return;
        }
        
        if (res.status === 404) {
            alert(`Không tìm thấy dữ liệu cho mã ${sym}. Vui lòng thử lại mã khác.`);
            return;
        }
        
        const resJson = await res.json();
        if (resJson.status === "success") {
            renderStockData(
                resJson.data, 
                resJson.ai_reasoning, 
                resJson.ml_prediction, 
                resJson.pattern_match, 
                resJson.zero_loss_metrics, 
                resJson.zero_dinh_metrics
            );
        }
    } catch (e) {
        console.error("Lỗi đánh giá cổ phiếu:", e);
    } finally {
        if (searchBtn) searchBtn.innerText = "🔍 Chẩn Đoán VSA";
    }
}

function renderStockData(data, aiReasoning, mlPrediction, patternMatch, zeroLossMetrics, zeroDinhMetrics) {
    const score = Number(data.score) || 0;
    const scoreEl = document.getElementById("vsaScoreVal");
    if (scoreEl) scoreEl.innerText = Math.round(score);
    
    const pill = document.getElementById("stockBadge");
    const statusText = data.recommendation_status || "Theo dõi";
    if (pill) {
        pill.innerText = statusText;
        if (statusText.includes("Múc") || score >= 75) {
            pill.className = "inline-block mt-2 px-3 py-1 rounded-full text-xs font-bold bg-emerald-950 text-emerald-300 border border-emerald-500/30";
        } else if (statusText.includes("Sút") || score <= 35) {
            pill.className = "inline-block mt-2 px-3 py-1 rounded-full text-xs font-bold bg-rose-950 text-rose-300 border border-rose-500/30";
        } else {
            pill.className = "inline-block mt-2 px-3 py-1 rounded-full text-xs font-bold bg-amber-950 text-amber-300 border border-amber-500/30";
        }
    }

    const phaseBadge = document.getElementById("stockPhaseBadge");
    if (phaseBadge) {
        phaseBadge.innerText = data.phase_name || (score >= 70 ? "Pha Đẩy Giá (Markup / Pha E)" : (score <= 35 ? "Pha Phân Phối (Distribution)" : "Pha Tích Lũy / Rũ Bỏ"));
    }

    const phaseDescEl = document.getElementById("vsaPhaseDesc");
    if (phaseDescEl) {
        phaseDescEl.innerText = data.recommendation_desc || "Biên độ dao động siết chặt (Spread hẹp) quanh MA20. Lực bán cạn kiệt thể hiện qua khối lượng dưới trung bình, sẵn sàng cho nhịp đẩy giá.";
    }
    
    const curPrice = data.latest_price ?? data.indicators?.price ?? 0;
    const priceChgPct = data.price_change_pct ?? 0;
    const closeEl = document.getElementById("closeVal");
    if (closeEl) {
        const chgSign = priceChgPct >= 0 ? '+' : '';
        const chgColor = priceChgPct >= 0 ? 'text-emerald-400' : 'text-rose-400';
        closeEl.innerHTML = `${curPrice > 0 ? curPrice.toFixed(2) : '--'} <span class="text-xs font-bold ${chgColor}">(${chgSign}${priceChgPct.toFixed(2)}%)</span>`;
    }
    
    const volRatio = data.indicators?.volume_ratio ?? 0;
    const volEl = document.getElementById("volR10Val");
    if (volEl) {
        const volTag = volRatio <= 0.85 ? '(Kiệt Cung)' : (volRatio >= 1.5 ? '(Bùng Nổ)' : '(Hấp Thụ)');
        volEl.innerHTML = `${volRatio > 0 ? volRatio.toFixed(2) : '--'}x <span class="text-xs font-bold text-slate-400">${volTag}</span>`;
    }
    
    const ma20 = data.indicators?.ma20 ?? 0;
    const ma50 = data.indicators?.ma50 ?? 0;
    const isAboveMa20 = curPrice >= ma20;
    const isAboveMa50 = curPrice >= ma50;
    const maEl = document.getElementById("maPosVal");
    if (maEl) {
        maEl.innerHTML = `&gt; ${isAboveMa20 ? 'MA20' : '<span class="text-rose-400">&lt;MA20</span>'} &amp; &gt; ${isAboveMa50 ? 'MA50' : '<span class="text-rose-400">&lt;MA50</span>'}`;
    }
    
    const rsiVal = data.indicators?.rsi ?? 0;
    const rsiEl = document.getElementById("rsiVal");
    if (rsiEl) {
        rsiEl.innerText = rsiVal > 0 ? rsiVal.toFixed(1) : '--';
    }
    
    // Optional legacy indicators (safeguarded)
    const desc = data.recommendation_desc || "";
    const t1El = document.getElementById("tier1Indicator");
    if (t1El) t1El.className = `tier-card ${desc.includes("Điểm Cược") ? "active" : ""}`;
    const t2El = document.getElementById("tier2Indicator");
    if (t2El) t2El.className = `tier-card ${desc.includes("Pocket") ? "active" : ""}`;
    const t3El = document.getElementById("tier3Indicator");
    if (t3El) t3El.className = `tier-card ${desc.includes("Điểm BU") || desc.includes("Pivot") ? "active" : ""}`;
    const t4El = document.getElementById("tier4Indicator");
    if (t4El) t4El.className = `tier-card ${desc.includes("Breakout") || desc.includes("Điểm Nổ") ? "active" : ""}`;
    
    loadSectorWave(data.sector_id || "NGAN_HANG");
    
    window.lastEvaluationResult = { data, aiReasoning, mlPrediction, patternMatch, zeroLossMetrics, zeroDinhMetrics };
    // Luôn cập nhật đầy đủ dữ liệu cho Tab 2 để đồng bộ 100%
    renderMLAndPatternData(mlPrediction, patternMatch, zeroLossMetrics, zeroDinhMetrics, data);
    
    if (aiReasoning) {
        const sauEl = document.getElementById("sauFomoText");
        if (sauEl) sauEl.innerHTML = formatMd(aiReasoning.sau_fomo || "Đang phân tích tâm lý dòng tiền...");

        const hqEl = document.getElementById("hqAnalysisText");
        if (hqEl) hqEl.innerHTML = formatMd(aiReasoning.hue_quyen || data.recommendation_desc);

        const dauEl = document.getElementById("dauAdviceText");
        if (dauEl) dauEl.innerHTML = formatMd(aiReasoning.be_dau || "Luôn giữ kỷ luật Zero-Loss nhé!");
        
        if (aiReasoning.diagnosis) {
            renderAcademicDiagnosis(aiReasoning.diagnosis, data);
        }
    }
}


function renderMLAndPatternData(ml, pat, zeroLoss, zeroDinh, data) {
    // 1. Thị trường & Sóng ngành
    const regimeBadge = document.getElementById("mlMarketRegimeBadge");
    if (regimeBadge) {
        const reg = (ml && ml.market_regime) || "SIDEWAY";
        regimeBadge.innerText = reg;
        regimeBadge.className = `regime-pill ${reg.toLowerCase()}`;
    }
    const secScoreVal = document.getElementById("mlSectorScoreVal");
    if (secScoreVal) {
        const sVal = (ml && ml.sector_wave_score != null) ? ml.sector_wave_score : (data?.sector_score ?? 50.0);
        secScoreVal.innerText = Number(sVal).toFixed(1);
    }
    
    // 2. TẦNG 1: Điểm Cược Zero-Loss
    const t1 = (ml && ml.tier1_cuoc) || {};
    const p1 = (t1.probability_pct != null) ? t1.probability_pct : (data?.score ? Math.min(85, Math.max(35, data.score * 0.75)) : 50.0);
    const p1El = document.getElementById("mlT1Prob");
    if (p1El) p1El.innerText = `${p1.toFixed(1)}%`;
    const bar1 = document.getElementById("mlT1Bar");
    if (bar1) bar1.style.width = `${Math.min(100, Math.max(0, p1))}%`;
    const st1 = document.getElementById("mlT1Status");
    if (st1) st1.innerText = `Đánh giá: ${t1.evaluation || (p1 >= 60 ? 'Ưu tú' : (p1 >= 50 ? 'Đạt yêu cầu' : 'Rủi ro'))} (Chuẩn: >=${t1.threshold_pct || 60}%)`;
    const act1 = document.getElementById("mlT1Action");
    if (act1) {
        const rec1 = (t1.is_recommended != null) ? t1.is_recommended : (p1 >= 60);
        act1.innerText = rec1 ? "✅ MÚC CƯỢC 1/8" : "⛔ Chưa đạt chuẩn";
        act1.style.color = rec1 ? "#10B981" : "#94A3B8";
    }
    const zlText = document.getElementById("mlZeroLossText");
    if (zlText) {
        if (zeroLoss && zeroLoss.min_close_base != null) {
            const isSafe = zeroLoss.is_safe;
            zlText.innerHTML = `Đáy nền: <strong>${zeroLoss.min_close_base.toFixed(2)}</strong> | Cách đáy: <strong>${zeroLoss.dist_to_base_pct > 0 ? '+' : ''}${zeroLoss.dist_to_base_pct.toFixed(2)}%</strong> ${isSafe ? '✅ (Chuẩn Zero-Loss &le; 2.5%)' : '⚠️ (>2.5% cách đáy)'}`;
        } else {
            zlText.innerText = "Chưa đủ dữ liệu nền kiệt cung 15 phiên";
        }
    }
    const t1Tag = document.getElementById("tier1MlProb");
    if (t1Tag) t1Tag.innerText = `ML: ${p1.toFixed(0)}%`;

    // 3. TẦNG 2: Điểm Đẩy Nền Pocket
    const t2 = (ml && ml.tier2_pocket) || {};
    const p2 = (t2.probability_pct != null) ? t2.probability_pct : (data?.score ? Math.min(80, Math.max(20, data.score * 0.4)) : 30.0);
    const p2El = document.getElementById("mlT2Prob");
    if (p2El) p2El.innerText = `${p2.toFixed(1)}%`;
    const bar2 = document.getElementById("mlT2Bar");
    if (bar2) bar2.style.width = `${Math.min(100, Math.max(0, p2))}%`;
    const st2 = document.getElementById("mlT2Status");
    if (st2) st2.innerText = `Đánh giá: ${t2.evaluation || (p2 >= 55 ? 'Ưu tú' : (p2 >= 45 ? 'Đạt yêu cầu' : 'Rủi ro'))} (Chuẩn: >=${t2.threshold_pct || 55}%)`;
    const act2 = document.getElementById("mlT2Action");
    if (act2) {
        const rec2 = (t2.is_recommended != null) ? t2.is_recommended : (p2 >= 55);
        act2.innerText = rec2 ? "✅ GIA TĂNG VỊ THẾ" : "⛔ Chưa kích hoạt";
        act2.style.color = rec2 ? "#F59E0B" : "#94A3B8";
    }
    const pocketText = document.getElementById("mlPocketCondText");
    if (pocketText) {
        const vr = data?.indicators?.volume_ratio || 0;
        pocketText.innerHTML = `Khối lượng hiện tại: <strong>${vr.toFixed(2)}x TB10</strong> ${vr <= 1.4 ? '✅ (Đạt chuẩn hấp thụ cung)' : '⚠️ (Vol chưa siết)'}`;
    }
    const t2Tag = document.getElementById("tier2MlProb");
    if (t2Tag) t2Tag.innerText = `ML: ${p2.toFixed(0)}%`;

    // 4. TẦNG 3: Điểm Pivot / Nổ Zero Đỉnh
    const t3 = (ml && ml.tier3_pivot) || {};
    const p3 = (t3.probability_pct != null) ? t3.probability_pct : (data?.score ? Math.min(85, Math.max(15, data.score * 0.35)) : 25.0);
    const p3El = document.getElementById("mlT3Prob");
    if (p3El) p3El.innerText = `${p3.toFixed(1)}%`;
    const bar3 = document.getElementById("mlT3Bar");
    if (bar3) bar3.style.width = `${Math.min(100, Math.max(0, p3))}%`;
    const st3 = document.getElementById("mlT3Status");
    if (st3) st3.innerText = `Đánh giá: ${t3.evaluation || (p3 >= 60 ? 'Ưu tú' : (p3 >= 45 ? 'Đạt yêu cầu' : 'Rủi ro'))} (Chuẩn: >=${t3.threshold_pct || 60}%)`;
    const act3 = document.getElementById("mlT3Action");
    if (act3) {
        const rec3 = (t3.is_recommended != null) ? t3.is_recommended : (p3 >= 60);
        act3.innerText = rec3 ? "✅ NỔ AN TOÀN" : "⚠️ Cảnh giác bẫy nổ xịt";
        act3.style.color = rec3 ? "#60A5FA" : "#EF4444";
    }
    const zdText = document.getElementById("mlZeroDinhText");
    if (zdText) {
        if (zeroDinh && zeroDinh.has_recent_breakout) {
            zdText.innerHTML = `Phiên nổ ${zeroDinh.break_date} (Nửa thân nến: <strong>${zeroDinh.half_body_level}</strong>) &rarr; <strong>${zeroDinh.status_text}</strong>`;
        } else {
            zdText.innerText = "Chưa có phiên nổ bùng nổ trong 5 phiên gần nhất";
        }
    }
    const t3Tag = document.getElementById("tier3MlProb");
    if (t3Tag) t3Tag.innerText = `ML: ${p3.toFixed(0)}%`;

    // 5. SO KHỚP MẪU HÌNH THỰC CHIẾN (PATTERN MATCHER)
    if (pat && pat.status === "success") {
        document.getElementById("pmPatternName").innerText = pat.best_match_pattern || "Mẫu hình tích lũy VSA";
        document.getElementById("pmSimilarityScore").innerText = `${(pat.similarity_score_pct || 0).toFixed(1)}%`;
        document.getElementById("pmReferenceStock").innerText = pat.reference_stock || "--";
        document.getElementById("pmHistoricalResult").innerText = pat.historical_result || "--";
        document.getElementById("pmCurrentPhase").innerText = pat.current_phase || "--";
        document.getElementById("pmDisciplineCheck").innerText = (pat.similarity_score_pct >= 80) ? "⭐ Khớp cao với ca mẫu" : "Đang kiểm định thêm";
        document.getElementById("pmPatternNote").innerText = pat.pattern_note || "Tuân thủ chặt chẽ điểm dừng lỗ và quản trị danh mục.";

        const imgContainer = document.getElementById("pmImageContainer");
        const imgName = document.getElementById("pmImageName");
        const imgLink = document.getElementById("pmImageLink");
        const imgInd = document.getElementById("pmImageIndicators");
        if (imgContainer) {
            if (pat.image_file) {
                imgContainer.classList.remove("hidden");
                if (imgName) imgName.innerText = pat.image_file;
                if (imgLink) imgLink.href = `/chart_images/${pat.image_file}`;
                if (imgInd) imgInd.innerHTML = pat.image_indicators ? `<strong>Tín hiệu chỉ báo:</strong> ${pat.image_indicators}` : "";
            } else {
                imgContainer.classList.add("hidden");
            }
        }
    } else {
        document.getElementById("pmPatternName").innerText = "Chưa có dữ liệu so khớp mẫu hình";
        document.getElementById("pmSimilarityScore").innerText = "--%";
        document.getElementById("pmReferenceStock").innerText = "--";
        document.getElementById("pmHistoricalResult").innerText = "--";
        document.getElementById("pmCurrentPhase").innerText = "--";
        document.getElementById("pmDisciplineCheck").innerText = "--";
        document.getElementById("pmPatternNote").innerText = pat?.message || "Hệ thống cần ít nhất 25 phiên giao dịch để trích xuất vân sóng giá và khối lượng.";
        const imgContainer = document.getElementById("pmImageContainer");
        if (imgContainer) imgContainer.classList.add("hidden");
    }
}

function renderAcademicDiagnosis(diag, data) {
    if (!diag) return;
    const sym = diag.symbol || data.symbol || 'CP';
    document.getElementById("diagSymbolBadge").innerText = sym;
    document.getElementById("diagSubInfo").innerText = `${diag.phase_name || 'Đang cập nhật pha'} • Mẫu hình: ${diag.pattern_name || 'Chuẩn VSA'}`;
    
    const actionEl = document.getElementById("diagActionBadge");
    actionEl.innerText = diag.action || 'THEO DÕI CHỜ TÍN HIỆU';
    const badgeType = diag.badge_type || 'warning';
    actionEl.className = `diag-action-pill pill-${badgeType}`;
    
    const fullText = diag.behavior_analysis || '';
    const parts = fullText.split(/\*\*\d+\.\s+/);
    if (parts.length >= 6) {
        const p1 = parts[1].replace(/^[^\n]*\n+/, '');
        const p2 = parts[2].replace(/^[^\n]*\n+/, '');
        const p3 = parts[3].replace(/^[^\n]*\n+/, '');
        const p4 = parts[4].replace(/^[^\n]*\n+/, '');
        const p5 = parts[5].replace(/^[^\n]*\n+/, '');
        
        document.getElementById("pillarSupplyDemand").innerHTML = formatMd(p1.trim());
        document.getElementById("pillarElasticity").innerHTML = formatMd(p2.trim());
        document.getElementById("pillarSectorContext").innerHTML = formatMd(p3.trim());
        document.getElementById("pillarCaseStudies").innerHTML = formatMd(p4.trim());
        const p5El = document.getElementById("pillarMLDiagnosis");
        if (p5El) p5El.innerHTML = formatMd(p5.trim());
    } else if (parts.length >= 5) {
        const p1 = parts[1].replace(/^[^\n]*\n+/, '');
        const p2 = parts[2].replace(/^[^\n]*\n+/, '');
        const p3 = parts[3].replace(/^[^\n]*\n+/, '');
        const p4 = parts[4].replace(/^[^\n]*\n+/, '');
        
        document.getElementById("pillarSupplyDemand").innerHTML = formatMd(p1.trim());
        document.getElementById("pillarElasticity").innerHTML = formatMd(p2.trim());
        document.getElementById("pillarSectorContext").innerHTML = formatMd(p3.trim());
        document.getElementById("pillarCaseStudies").innerHTML = formatMd(p4.trim());
    } else {
        document.getElementById("pillarSupplyDemand").innerHTML = formatMd(fullText);
        document.getElementById("pillarElasticity").innerHTML = "Đang đối chiếu dữ liệu xung lực...";
        document.getElementById("pillarSectorContext").innerHTML = "Đang kiểm tra sóng ngành liên quan...";
        document.getElementById("pillarCaseStudies").innerHTML = "Đang đối chiếu 12 case studies thực chiến...";
    }
    
    const plan = diag.actionable_plan || {};
    const pE1 = document.getElementById("planEntry1"); if (pE1) pE1.innerText = plan.entry_point_1 || 'Chưa đạt điểm mua';
    const pE2 = document.getElementById("planEntry2"); if (pE2) pE2.innerText = plan.entry_point_2 || 'Không khuyến nghị Margin';
    const pSL = document.getElementById("planStopLoss"); if (pSL) pSL.innerText = plan.stop_loss || `Cắt lỗ dứt khoát tại -2.5%`;
    const pTP = document.getElementById("planTakeProfit"); if (pTP) pTP.innerText = plan.take_profit || `Mục tiêu 1 (+15%) | Mục tiêu 2 (+30%)`;
    const pAlloc = document.getElementById("planAllocation"); if (pAlloc) pAlloc.innerHTML = `<strong>Quy tắc phân bổ vốn:</strong> ${plan.capital_allocation || 'Tối đa 4 cổ phiếu trong danh mục (25% vốn/mã). Mỗi mã chia làm 2 đợt giải ngân.'}`;
    const pWarn = document.getElementById("planRiskWarning"); 
    if (pWarn && diag.risk_warning) {
        pWarn.innerHTML = `⚠️ <strong>Cảnh báo:</strong> ${formatMd(diag.risk_warning)}`;
    }
}


async function loadSectorWave(sectorId) {
    const secId = sectorId || (document.getElementById("sectorSelect")?.value) || "NGAN_HANG";
    
    // Đồng bộ ô lựa chọn select dropdown
    const sel = document.getElementById("sectorSelect");
    if (sel && sel.value !== secId) {
        sel.value = secId;
    }

    // Cập nhật trạng thái active nổi bật cho 8 nút bấm nhanh
    const pills = document.querySelectorAll(".sector-pill-btn");
    pills.forEach(p => {
        if (p.getAttribute("data-sector") === secId) {
            p.className = "sector-pill-btn px-2.5 py-1 rounded-lg text-xs font-black transition cursor-pointer bg-sky-600 text-white border border-sky-400 shadow";
        } else {
            p.className = "sector-pill-btn px-2.5 py-1 rounded-lg text-xs font-semibold transition cursor-pointer bg-slate-900 text-slate-300 hover:text-white border border-slate-700/60";
        }
    });

    try {
        const dateVal = document.getElementById("scanDateInput")?.value;
        const url = `/api/sector_wave/${secId}${dateVal ? '?target_date=' + encodeURIComponent(dateVal) : ''}`;
        
        const res = await fetch(url);
        if (!res.ok) return;
        const resJson = await res.json();
        const sec = resJson.data;
        if (!sec) return;
        
        const badgeEl = document.getElementById("sectorBadge");
        if (badgeEl) {
            badgeEl.innerText = sec.status || sec.sector_name || "Theo dõi";
            if (sec.state === "MO_RONG_A" || sec.state === "MO_RONG_B" || sec.score >= 70) {
                badgeEl.className = "tag-pill bg-emerald-500/25 text-emerald-300 border border-emerald-500/40 font-bold";
            } else if (sec.state === "SOI_DO_DUONG" || sec.score >= 55) {
                badgeEl.className = "tag-pill bg-sky-500/25 text-sky-300 border border-sky-500/40 font-bold";
            } else if (sec.score >= 40) {
                badgeEl.className = "tag-pill bg-amber-500/25 text-amber-300 border border-amber-500/40 font-bold";
            } else {
                badgeEl.className = "tag-pill bg-rose-500/25 text-rose-300 border border-rose-500/40 font-bold";
            }
        }

        const scoreEl = document.getElementById("sectorScoreBadge");
        if (scoreEl && sec.score !== undefined) {
            scoreEl.innerText = `Điểm sóng: ${sec.score.toFixed(1)}/100`;
            scoreEl.className = sec.score >= 60 ? "text-xs font-bold text-emerald-400 font-mono" : (sec.score >= 45 ? "text-xs font-bold text-amber-400 font-mono" : "text-xs font-bold text-rose-400 font-mono");
        }

        const scoutEl = document.getElementById("scoutWolfVal");
        if (scoutEl) scoutEl.innerText = sec.scout_wolf ? `${sec.scout_wolf} (Súng hiệu ${sec.scout_date || 'gần nhất'})` : "Chưa xuất hiện";

        const leaderEl = document.getElementById("leaderVal");
        if (leaderEl) leaderEl.innerText = sec.leader ? `${sec.leader} (Điểm VSA: ${sec.leader_score})` : "--";

        const tier1El = document.getElementById("tier1PctVal");
        if (tier1El) tier1El.innerText = `${sec.tier1_above_ma50_pct ? sec.tier1_above_ma50_pct.toFixed(1) : 0}%`;

        const marginEl = document.getElementById("marginRecVal");
        if (marginEl) marginEl.innerText = sec.margin_recommendation || "CHƯA DÙNG MARGIN";
    } catch (e) {
        console.error("Lỗi tải sóng ngành:", e);
    }
}

function onSectorSelectChange() {
    const sel = document.getElementById("sectorSelect");
    if (sel) {
        loadSectorWave(sel.value);
    }
}
window.onSectorSelectChange = onSectorSelectChange;
window.loadSectorWave = loadSectorWave;

// ==================== 3 MAIN TABS NAVIGATION & LAZY LOADING ====================
let currentActiveMainTab = 'tab1';

function switchView(tabId) {
    const cleanId = (tabId || 'tab1').toLowerCase();
    currentActiveMainTab = cleanId;

    // 1. Switch all views and button highlights
    ['tab1', 'tab2', 'tab3'].forEach(t => {
        const idName = t.charAt(0).toUpperCase() + t.slice(1); // 'Tab1', 'Tab2', 'Tab3'
        const viewEl = document.getElementById('view' + idName);
        const b = document.getElementById('btn' + idName) || document.getElementById('mainBtn' + idName);
        
        if (t === cleanId) {
            if (viewEl) {
                viewEl.classList.remove('hidden');
                viewEl.style.display = 'block';
            }
            if (b) {
                b.className = "active-tab px-4 py-2 rounded-lg text-xs md:text-sm font-bold transition flex items-center gap-2 text-white border border-emerald-500";
            }
        } else {
            if (viewEl) {
                viewEl.classList.add('hidden');
                viewEl.style.display = 'none';
            }
            if (b) {
                b.className = "px-4 py-2 rounded-lg text-xs md:text-sm font-bold transition flex items-center gap-2 text-slate-300 hover:text-white border border-transparent";
            }
        }
    });

    // 2. Lazy loading & data synchronization
    if (cleanId === 'tab1') {
        // Tab 1 is active
    } else if (cleanId === 'tab2') {
        const symInput = document.getElementById("symbolInput");
        const bdiSymInput = document.getElementById("bdiSymbolInput");
        if (symInput && bdiSymInput && symInput.value && !bdiSymInput.value) {
            bdiSymInput.value = symInput.value;
        }
        const dateInput = document.getElementById("dateInput");
        const bdiDateInput = document.getElementById("bdiDateInput");
        if (dateInput && bdiDateInput && dateInput.value && !bdiDateInput.value) {
            bdiDateInput.value = dateInput.value;
        }
        loadTrackedPositions();
        loadWatchlistPositions();
        if (window.lastEvaluationResult) {
            renderMLAndPatternData(
                window.lastEvaluationResult.mlPrediction,
                window.lastEvaluationResult.patternMatch,
                window.lastEvaluationResult.zeroLossMetrics,
                window.lastEvaluationResult.zeroDinhMetrics,
                window.lastEvaluationResult.data
            );
        }
    } else if (cleanId === 'tab3') {
        const currentSec = document.getElementById("sectorSelect")?.value || "NGAN_HANG";
        loadSectorWave(currentSec);
        if (!currentScanData || (!currentScanData.tier1_cuoc?.length && !currentScanData.tier2_pocket?.length && !currentScanData.tier3_pivot?.length)) {
            runScreener();
        }
    }
}

function switchMainTab(tabId) {
    switchView(tabId);
}

// Expose globally so inline onclick handlers always find them
window.switchView = switchView;
window.switchMainTab = switchMainTab;


// ==================== TAB 3: BỘ LỌC QUÉT TOÀN BỘ THỊ TRƯỜNG & SÓNG NGÀNH ====================
async function runScreener() {
    const container = document.getElementById("scanResultsContent");
    if (!container) return;
    
    const exchangeSelect = document.getElementById("scanExchangeSelect");
    const exchange = exchangeSelect ? exchangeSelect.value : "HOSE";
    const exchangeText = exchangeSelect ? exchangeSelect.options[exchangeSelect.selectedIndex].text : "Sàn HOSE";
    
    container.innerHTML = `<div class="p-8 text-center text-slate-300 text-xs flex flex-col items-center justify-center gap-2">
        <div class="inline-block animate-spin rounded-full h-6 w-6 border-b-2 border-emerald-400"></div>
        <span>⚡ Đang quét toàn diện <b>${exchangeText}</b> theo chuẩn BDI Engine (Thuật toán số 2, Sbar, Kiệt cung)... Vui lòng chờ...</span>
    </div>`;
    
    const scanDate = document.getElementById("scanDateInput")?.value;
    let url = `/api/scan_3_tiers?exchange=${exchange}`;
    if (scanDate) {
        url += `&target_date=${scanDate}`;
    }
    
    try {
        const res = await fetch(url);
        if (!res.ok) {
            container.innerHTML = `<div class="p-8 text-center text-rose-400 text-xs">❌ Lỗi quét thị trường (${res.status}). Vui lòng kiểm tra lại.</div>`;
            return;
        }
        const resJson = await res.json();
        currentScanData = resJson.data || { tier1_cuoc: [], tier2_pocket: [], tier3_pivot: [], ml_picks: [], no2_candidates: [] };
        currentScanData.no2 = resJson.data?.no2_candidates || [];
        
        // Fetch Super Stock Radar in parallel
        try {
            let ssUrl = "/api/super_stock_radar?min_score=50.0";
            if (scanDate) ssUrl += `&target_date=${scanDate}`;
            const ssRes = await fetch(ssUrl);
            if (ssRes.ok) {
                const ssJson = await ssRes.json();
                currentScanData.super_stock = ssJson.data || [];
            }
        } catch (ssErr) {
            console.warn("Không tải được Super Stock Radar:", ssErr);
            currentScanData.super_stock = [];
        }

        // Fetch No2 Radar in parallel if not already populated
        if (!currentScanData.no2 || currentScanData.no2.length === 0) {
            try {
                let no2Url = "/api/no2_radar?min_score=65.0";
                if (scanDate) no2Url += `&target_date=${scanDate}`;
                const no2Res = await fetch(no2Url);
                if (no2Res.ok) {
                    const no2Json = await no2Res.json();
                    currentScanData.no2 = no2Json.data || [];
                }
            } catch (no2Err) {
                console.warn("Không tải được No2 Radar:", no2Err);
                currentScanData.no2 = [];
            }
        }

        const t1 = currentScanData.tier1_cuoc.length;
        const t2 = currentScanData.tier2_pocket.length;
        const t3 = currentScanData.tier3_pivot.length;
        const tml = (currentScanData.ml_picks || []).length;
        const tss = (currentScanData.super_stock || []).length;
        const tno2 = (currentScanData.no2 || []).length;

        const countAllEl = document.getElementById("countAll");
        if (countAllEl) countAllEl.innerText = t1 + t2 + t3;
        const countNo2El = document.getElementById("countNo2");
        if (countNo2El) countNo2El.innerText = tno2;
        const countT1El = document.getElementById("countTier1");
        if (countT1El) countT1El.innerText = t1;
        const countT2El = document.getElementById("countTier2");
        if (countT2El) countT2El.innerText = t2;
        const countT3El = document.getElementById("countTier3");
        if (countT3El) countT3El.innerText = t3;
        const countMlEl = document.getElementById("countMlPicks");
        if (countMlEl) countMlEl.innerText = tml;
        const countSsEl = document.getElementById("countSuperStock");
        if (countSsEl) countSsEl.innerText = tss;
        
        updateScanTabUI();
        renderScanResults();
    } catch (e) {
        container.innerHTML = `<div class="p-8 text-center text-rose-400 text-xs">Lỗi khi quét: ${e}</div>`;
    }
}

async function loadNo2RadarOnly() {
    const container = document.getElementById("scanResultsContent");
    if (!container) return;
    container.innerHTML = '<div class="p-8 text-center text-purple-300 text-xs">🏆 Đang quét toàn diện Radar Săn Siêu Cổ Nền Số 2 (Strategy No2)... Vui lòng chờ...</div>';
    
    const scanDate = document.getElementById("scanDateInput")?.value;
    let url = "/api/no2_radar?min_score=65.0";
    if (scanDate) url += `&target_date=${scanDate}`;
    
    try {
        const res = await fetch(url);
        if (!res.ok) {
            container.innerHTML = `<div class="p-8 text-center text-rose-400 text-xs">❌ Lỗi quét Radar No2 (${res.status}).</div>`;
            return;
        }
        const j = await res.json();
        if (!currentScanData) currentScanData = {};
        currentScanData.no2 = j.data || [];
        
        const countNo2El = document.getElementById("countNo2");
        if (countNo2El) countNo2El.innerText = currentScanData.no2.length;
        
        activeScanTier = 'no2';
        updateScanTabUI();
        renderScanResults();
    } catch (e) {
        container.innerHTML = `<div class="p-8 text-center text-rose-400 text-xs">Lỗi: ${e}</div>`;
    }
}

async function loadSuperStockRadarOnly() {
    const container = document.getElementById("scanResultsContent");
    if (!container) return;
    container.innerHTML = '<div class="p-8 text-center text-amber-300 text-xs">💎 Đang quét toàn diện Radar Siêu Cổ Phiếu AI trên 20 năm dữ liệu... Vui lòng chờ...</div>';
    
    const scanDate = document.getElementById("scanDateInput")?.value;
    let url = "/api/super_stock_radar?min_score=50.0";
    if (scanDate) url += `&target_date=${scanDate}`;
    
    try {
        const res = await fetch(url);
        if (!res.ok) {
            container.innerHTML = `<div class="p-8 text-center text-rose-400 text-xs">❌ Lỗi quét Radar Siêu Cổ Phiếu (${res.status}).</div>`;
            return;
        }
        const j = await res.json();
        if (!currentScanData) currentScanData = {};
        currentScanData.super_stock = j.data || [];
        
        const countSsEl = document.getElementById("countSuperStock");
        if (countSsEl) countSsEl.innerText = currentScanData.super_stock.length;
        
        activeScanTier = 'super_stock';
        updateScanTabUI();
        renderScanResults();
    } catch (e) {
        container.innerHTML = `<div class="p-8 text-center text-rose-400 text-xs">Lỗi: ${e}</div>`;
    }
}

function filterScanTier(tier) {
    activeScanTier = tier;
    updateScanTabUI();
    renderScanResults();
}

function updateScanTabUI() {
    const tabMap = { 
        'all': 'tabAll',
        'no2': 'tabNo2',
        'super_stock': 'tabSuperStock',
        'ml_picks': 'tabMlPicks', 
        'tier1': 'tabTier1', 
        'tier2': 'tabTier2', 
        'tier3': 'tabTier3' 
    };
    Object.keys(tabMap).forEach(k => {
        const el = document.getElementById(tabMap[k]);
        if (el) {
            if (k === activeScanTier) {
                if (k === 'no2') {
                    el.className = "scan-tab px-3 py-1.5 rounded-lg bg-gradient-to-r from-purple-600 to-indigo-600 text-white font-black transition shadow-lg";
                } else if (k === 'super_stock') {
                    el.className = "scan-tab px-3 py-1.5 rounded-lg bg-gradient-to-r from-amber-500 to-yellow-600 text-slate-950 font-black transition shadow-lg";
                } else {
                    el.className = "scan-tab px-3 py-1.5 rounded-lg bg-emerald-600 text-white font-bold transition";
                }
            } else {
                el.className = "scan-tab px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 font-bold transition";
            }
        }
    });
}

function filterScanSearch() {
    renderScanResults();
}

function inspectStockFromScreener(sym) {
    const symInput = document.getElementById("symbolInput");
    if (symInput) symInput.value = sym;
    switchView('tab1');
    evaluateStock();
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function selectFromScan(sym) {
    inspectStockFromScreener(sym);
}

const SECTOR_NAMES = {
    "VCB": "Ngân hàng", "TCB": "Ngân hàng", "VPB": "Ngân hàng", "MBB": "Ngân hàng", "ACB": "Ngân hàng", "STB": "Ngân hàng", "CTG": "Ngân hàng", "BID": "Ngân hàng", "HDB": "Ngân hàng", "TPB": "Ngân hàng", "SHB": "Ngân hàng", "SSB": "Ngân hàng",
    "SSI": "Chứng khoán", "VND": "Chứng khoán", "VCI": "Chứng khoán", "HCM": "Chứng khoán", "SHS": "Chứng khoán", "MBS": "Chứng khoán", "VIX": "Chứng khoán", "FTS": "Chứng khoán", "BSI": "Chứng khoán", "CTS": "Chứng khoán", "AGR": "Chứng khoán",
    "VHM": "Bất động sản", "VIC": "Bất động sản", "VRE": "Bất động sản", "NVL": "Bất động sản", "PDR": "Bất động sản", "DIG": "Bất động sản", "DXG": "Bất động sản", "KDH": "Bất động sản", "NLG": "Bất động sản", "KBC": "Bất động sản", "CEO": "Bất động sản", "TCH": "Bất động sản",
    "GAS": "Dầu khí", "PVD": "Dầu khí", "PVS": "Dầu khí", "BSR": "Dầu khí", "PLX": "Dầu khí", "PVT": "Dầu khí", "PVC": "Dầu khí",
    "HPG": "Thép", "HSG": "Thép", "NKG": "Thép", "VGS": "Thép", "TLH": "Thép",
    "DGC": "Hóa chất", "CSV": "Hóa chất", "DPM": "Phân bón", "DCM": "Phân bón", "BFC": "Phân bón", "GVR": "Cao su",
    "MWG": "Bán lẻ", "FRT": "Bán lẻ", "PNJ": "Bán lẻ", "DGW": "Bán lẻ", "MSN": "Bán lẻ", "VNM": "Thực phẩm", "DBC": "Nông nghiệp",
    "GMD": "Cảng biển", "HAH": "Cảng biển", "VSC": "Cảng biển", "VOS": "Cảng biển"
};

async function openSuperStockModal(sym) {
    const modal = document.getElementById("superStockDetailModal");
    if (!modal) return;
    
    modal.classList.remove("hidden");
    document.getElementById("ssModalTitle").innerText = `RADAR SIÊU CỔ PHIẾU: ${sym}`;
    document.getElementById("ssModalScore").innerText = "...";
    document.getElementById("ssModalBadge").innerText = "Đang tải dữ liệu...";
    document.getElementById("ssModalPillars").innerHTML = '<div class="p-4 text-center text-slate-400">Đang chạy mô hình AI đánh giá 5 trụ cột...</div>';
    document.getElementById("ssModalCapitalPlan").innerHTML = '';
    
    const inspectBtn = document.getElementById("ssModalInspectBtn");
    if (inspectBtn) {
        inspectBtn.onclick = () => {
            closeSuperStockModal();
            inspectStockFromScreener(sym);
        };
    }

    try {
        const scanDate = document.getElementById("scanDateInput")?.value;
        let url = `/api/super_stock_detail?symbol=${sym}`;
        if (scanDate) url += `&target_date=${scanDate}`;
        
        const res = await fetch(url);
        if (!res.ok) {
            document.getElementById("ssModalPillars").innerHTML = `<div class="p-4 text-rose-400 text-center">Lỗi tải dữ liệu (${res.status})</div>`;
            return;
        }
        const j = await res.json();
        const d = j.data;
        if (!d) return;

        document.getElementById("ssModalScore").innerText = `${d.super_stock_score}/100`;
        document.getElementById("ssModalBadge").innerText = d.tier_badge;
        document.getElementById("ssModalPrice").innerText = d.close.toFixed(2);
        
        const chgColor = d.chg_pct >= 0 ? 'text-emerald-400' : 'text-rose-400';
        const chgSign = d.chg_pct >= 0 ? '+' : '';
        document.getElementById("ssModalChg").innerHTML = `<span class="${chgColor} font-bold">${chgSign}${d.chg_pct.toFixed(2)}%</span>`;
        document.getElementById("ssModalVolRatio").innerText = `${d.vol_ratio.toFixed(2)}x`;
        document.getElementById("ssModalMfe").innerText = d.expected_mfe;

        // Render 5 Pillars
        let pilsHtml = '';
        const pilKeys = [
            { key: 'gio_dong', icon: '🌪️' },
            { key: 'dan_soi', icon: '🐺' },
            { key: 'nen_gia', icon: '🧱' },
            { key: 'xung_luc', icon: '⚡' },
            { key: 'tennis_ball', icon: '🎾' }
        ];

        pilKeys.forEach(pk => {
            const pil = d.pillars[pk.key];
            if (!pil) return;
            const barW = Math.min(100, Math.max(10, pil.score));
            const barColor = pil.score >= 80 ? 'bg-amber-400' : (pil.score >= 65 ? 'bg-emerald-400' : 'bg-sky-400');
            pilsHtml += `
                <div class="p-2.5 bg-slate-950/80 rounded-xl border border-slate-800 space-y-1">
                    <div class="flex justify-between items-center text-xs">
                        <span class="font-bold text-white flex items-center gap-1.5">
                            <span>${pk.icon}</span> <span>${pil.name}</span>
                        </span>
                        <div class="flex items-center gap-2">
                            <span class="text-slate-400 text-[11px]">${pil.status}</span>
                            <span class="font-mono font-bold text-white px-1.5 py-0.5 rounded bg-slate-800 text-[11px]">${pil.score}đ</span>
                        </div>
                    </div>
                    <div class="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
                        <div class="${barColor} h-full rounded-full" style="width: ${barW}%"></div>
                    </div>
                </div>
            `;
        });
        document.getElementById("ssModalPillars").innerHTML = pilsHtml;

        // Render Capital Plan
        const cp = d.capital_plan;
        let cpHtml = `
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px]">
                <div class="p-2 rounded-lg bg-slate-950 border border-slate-800">
                    <strong class="text-emerald-400 block mb-0.5">🟢 Tầng 1 (Điểm Cược):</strong>
                    <span>${cp.entry_bet}</span>
                </div>
                <div class="p-2 rounded-lg bg-slate-950 border border-slate-800">
                    <strong class="text-sky-400 block mb-0.5">🔵 Tầng 2 (Gia Tăng):</strong>
                    <span>${cp.entry_scale}</span>
                </div>
                <div class="p-2 rounded-lg bg-slate-950 border border-rose-500/30">
                    <strong class="text-rose-400 block mb-0.5">🛡️ Kỷ Luật Cắt Lỗ:</strong>
                    <span>${cp.stop_loss}</span>
                </div>
                <div class="p-2 rounded-lg bg-slate-950 border border-amber-500/30">
                    <strong class="text-amber-400 block mb-0.5">🎯 Mục Tiêu Sóng:</strong>
                    <span>${cp.target}</span>
                </div>
            </div>
            <div class="p-2 rounded-lg bg-slate-950/90 border border-slate-800 text-[11px] text-slate-300">
                <strong class="text-purple-400">⚡ Điều Kiện Margin:</strong> ${cp.margin_trigger}
            </div>
        `;
        document.getElementById("ssModalCapitalPlan").innerHTML = cpHtml;

    } catch (e) {
        document.getElementById("ssModalPillars").innerHTML = `<div class="p-4 text-rose-400 text-center">Lỗi: ${e}</div>`;
    }
}

function closeSuperStockModal() {
    const modal = document.getElementById("superStockDetailModal");
    if (modal) modal.classList.add("hidden");
}

async function openNo2Modal(sym) {
    const modal = document.getElementById("no2DetailModal");
    if (!modal) return;
    
    document.getElementById("no2ModalTitle").innerText = `CHIẾN LƯỢC No2: ${sym}`;
    document.getElementById("no2ModalSubtitle").innerText = `Săn Siêu Cổ Phiếu Nền Số 2 Trên Cao • Đậu Mầm Pro`;
    document.getElementById("no2ModalPillars").innerHTML = '<div class="p-4 text-center text-slate-400">⏳ Đang phân tích định lượng 6 tầng No2...</div>';
    document.getElementById("no2ModalCapitalPlan").innerHTML = '';
    modal.classList.remove("hidden");
    
    const inspectBtn = document.getElementById("no2ModalInspectBtn");
    if (inspectBtn) {
        inspectBtn.onclick = () => {
            closeNo2Modal();
            inspectStockFromScreener(sym);
        };
    }

    try {
        const scanDate = document.getElementById("scanDateInput")?.value;
        let url = `/api/no2_detail?symbol=${sym}`;
        if (scanDate) url += `&target_date=${scanDate}`;
        
        const res = await fetch(url);
        if (!res.ok) {
            document.getElementById("no2ModalPillars").innerHTML = `<div class="p-4 text-rose-400 text-center">Lỗi tải dữ liệu (${res.status})</div>`;
            return;
        }
        const j = await res.json();
        const d = j.data;
        if (!d) return;

        document.getElementById("no2ModalScore").innerText = `${d.no2_score}/100`;
        document.getElementById("no2ModalActionBadge").innerText = d.action_code || 'WATCH';
        document.getElementById("no2ModalBmsScore").innerText = `${d.bms_score ? d.bms_score.toFixed(1) : '--'}đ`;
        document.getElementById("no2ModalBmsTier").innerText = d.bms_tier || '';
        document.getElementById("no2ModalBaseLen").innerText = `${d.base2_duration_days || '--'} phiên`;
        document.getElementById("no2ModalBaseDepth").innerText = `Độ sâu: ${d.base2_depth_pct ? d.base2_depth_pct.toFixed(1) : '--'}%`;
        document.getElementById("no2ModalMinVol").innerText = `${d.min_vol_ratio_base2 !== undefined ? d.min_vol_ratio_base2.toFixed(2) : '--'}x`;

        // Render 6 Pillars
        let pilsHtml = '';
        const pilKeys = [
            { key: 't1_stage1', name: 'Tầng 1: Dấu Vết Nhịp Tăng 1 (+22% đến +65%)', icon: '🚀' },
            { key: 't2_trend_inflection', name: 'Tầng 2: Bẻ Cong Xu Hướng (Giá ≥ MA50 & MA100)', icon: '📈' },
            { key: 't3_base2_vcp', name: 'Tầng 3: Cấu Trúc Độ Nén Nền 2 (VCP Pro, Sâu ≤ 15%)', icon: '🧱' },
            { key: 't4_vsa_vdu', name: 'Tầng 4: Thanh Khoản Kiệt Quệ VSA (≤ 0.5x TB20)', icon: '💧' },
            { key: 't5_smd_obv', name: 'Tầng 5: Dòng Tiền Ngầm (OBV > WMA10 & RS Sức Mạnh)', icon: '🌊' },
            { key: 't6_bms_trigger', name: 'Tầng 6: Điểm Bấm Cò Chủ Động & Xung Lực BMS', icon: '⚡' }
        ];

        pilKeys.forEach(pk => {
            const pil = d.pillars ? d.pillars[pk.key] : null;
            if (!pil) return;
            const pScore = pil.score || (pil.passed ? 20.0 : 0.0);
            const barW = Math.min(100, Math.max(10, (pScore / 20.0) * 100));
            const barColor = pil.passed ? 'bg-purple-400' : 'bg-slate-700';
            const statusText = pil.passed ? '✅ ĐẠT' : '❌ CHƯA ĐẠT';
            pilsHtml += `
                <div class="p-2.5 bg-slate-950/80 rounded-xl border border-slate-800 space-y-1">
                    <div class="flex justify-between items-center text-xs">
                        <span class="font-bold text-white flex items-center gap-1.5">
                            <span>${pk.icon}</span> <span>${pk.name}</span>
                        </span>
                        <div class="flex items-center gap-2">
                            <span class="${pil.passed ? 'text-emerald-400' : 'text-slate-400'} font-bold text-[11px]">${statusText}</span>
                            <span class="font-mono font-bold text-white px-1.5 py-0.5 rounded bg-slate-800 text-[11px]">${pScore}đ</span>
                        </div>
                    </div>
                    <div class="text-[11px] text-slate-400">${pil.desc}</div>
                    <div class="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden mt-1">
                        <div class="${barColor} h-full rounded-full" style="width: ${barW}%"></div>
                    </div>
                </div>
            `;
        });
        document.getElementById("no2ModalPillars").innerHTML = pilsHtml;

        // Render Capital Plan
        const cp = d.capital_plan;
        if (cp) {
            let cpHtml = `
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px]">
                    <div class="p-2 rounded-lg bg-slate-950 border border-purple-500/30">
                        <strong class="text-purple-300 block mb-0.5">🟢 Vị Thế C1 (Cược Trong Nền):</strong>
                        <span>${cp.entry_c1}</span>
                    </div>
                    <div class="p-2 rounded-lg bg-slate-950 border border-sky-500/30">
                        <strong class="text-sky-400 block mb-0.5">🟡 Vị Thế P1 (Pocket Nhú Nền):</strong>
                        <span>${cp.entry_p1}</span>
                    </div>
                    <div class="p-2 rounded-lg bg-slate-950 border border-rose-500/30">
                        <strong class="text-rose-400 block mb-0.5">🛡️ Kỷ Luật Cắt Lỗ:</strong>
                        <span>${cp.stop_loss}</span>
                    </div>
                    <div class="p-2 rounded-lg bg-slate-950 border border-emerald-500/30">
                        <strong class="text-emerald-400 block mb-0.5">🎯 Mục Tiêu Sóng Nhịp 2:</strong>
                        <span>${cp.target}</span>
                    </div>
                </div>
                <div class="p-2 rounded-lg bg-slate-950/90 border border-slate-800 text-[11px] text-slate-300">
                    <strong class="text-amber-400">⚡ Điều Kiện Margin & Breakout B1:</strong> ${cp.entry_b1} | ${cp.margin_trigger}
                </div>
            `;
            document.getElementById("no2ModalCapitalPlan").innerHTML = cpHtml;
        }

    } catch (e) {
        document.getElementById("no2ModalPillars").innerHTML = `<div class="p-4 text-rose-400 text-center">Lỗi: ${e}</div>`;
    }
}

function closeNo2Modal() {
    const modal = document.getElementById("no2DetailModal");
    if (modal) modal.classList.add("hidden");
}

window.loadNo2RadarOnly = loadNo2RadarOnly;
window.openNo2Modal = openNo2Modal;
window.closeNo2Modal = closeNo2Modal;
window.loadSuperStockRadarOnly = loadSuperStockRadarOnly;
window.openSuperStockModal = openSuperStockModal;
window.closeSuperStockModal = closeSuperStockModal;


function renderScanResults() {
    const container = document.getElementById("scanResultsContent");
    if (!container) return;
    const query = (document.getElementById("scanSearchInput")?.value || '').trim().toUpperCase();
    
    let allItems = [];
    if (activeScanTier === 'all') {
        const set = new Set();
        [...(currentScanData.no2 || []), ...(currentScanData.super_stock || []), ...(currentScanData.ml_picks || []), ...(currentScanData.tier1_cuoc || []), ...(currentScanData.tier2_pocket || []), ...(currentScanData.tier3_pivot || [])].forEach(it => {
            if (!set.has(it.symbol)) {
                set.add(it.symbol);
                allItems.push(it);
            }
        });
    } else if (activeScanTier === 'no2') {
        allItems = currentScanData.no2 || [];
    } else if (activeScanTier === 'super_stock') {
        allItems = currentScanData.super_stock || [];
    } else if (activeScanTier === 'ml_picks') {
        allItems = currentScanData.ml_picks || [];
    } else if (activeScanTier === 'tier1') {
        allItems = currentScanData.tier1_cuoc || [];
    } else if (activeScanTier === 'tier2') {
        allItems = currentScanData.tier2_pocket || [];
    } else if (activeScanTier === 'tier3') {
        allItems = currentScanData.tier3_pivot || [];
    }

    if (query) {
        allItems = allItems.filter(item => item.symbol.includes(query) || (item.desc && item.desc.toUpperCase().includes(query)) || (item.sector && item.sector.toUpperCase().includes(query)));
    }

    if (allItems.length === 0) {
        container.innerHTML = `<div class="p-8 text-center text-slate-400 text-xs">Không có mã cổ phiếu nào phù hợp bộ lọc này hôm nay.</div>`;
        return;
    }

    // SPECIAL DEDICATED VIEW FOR STRATEGY No2 RADAR
    if (activeScanTier === 'no2') {
        let no2RowsHtml = '';
        allItems.forEach(p => {
            const chgColor = (p.chg_pct || 0) > 0 ? 'text-emerald-400' : ((p.chg_pct || 0) < 0 ? 'text-rose-400' : 'text-amber-400');
            const chgSign = (p.chg_pct || 0) >= 0 ? '+' : '';
            const closeVal = p.close ? p.close.toFixed(2) : '--';
            const chgVal = (p.chg_pct !== undefined && p.chg_pct !== null) ? `${chgSign}${p.chg_pct.toFixed(2)}%` : '--';
            
            // Action badge
            let actBadge = '<span class="text-[10px] px-2 py-0.5 rounded-full border bg-purple-950 text-purple-300 border-purple-500/50">C1: NÉN NỀN</span>';
            if (p.action_code === 'P1') {
                actBadge = '<span class="text-[10px] px-2 py-0.5 rounded-full border bg-amber-950 text-amber-300 border-amber-500/50 font-bold">P1: POCKET NHÚ</span>';
            } else if (p.action_code === 'B1') {
                actBadge = '<span class="text-[10px] px-2 py-0.5 rounded-full border bg-blue-950 text-blue-300 border-blue-500/50 font-bold">B1: BREAKOUT</span>';
            } else if (p.action_code === 'WATCH') {
                actBadge = '<span class="text-[10px] px-2 py-0.5 rounded-full border bg-slate-900 text-slate-300 border-slate-700">THEO DÕI</span>';
            }

            const scoreColor = p.no2_score >= 85 ? 'text-purple-300 font-black' : (p.no2_score >= 70 ? 'text-emerald-400 font-extrabold' : 'text-sky-400 font-bold');
            const bmsColor = (p.bms_score || 0) >= 70 ? 'text-amber-400 font-black' : 'text-slate-300';
            const sector = SECTOR_NAMES[p.symbol] || p.sector || 'Cơ bản';
            const s1Gain = p.stage1_gain_pct ? `+${p.stage1_gain_pct.toFixed(1)}%` : '--';
            const baseLen = p.base2_duration_days ? `${p.base2_duration_days}p` : '--';
            const baseDepth = p.base2_depth_pct ? `${p.base2_depth_pct.toFixed(1)}%` : '--';
            const minVol = (p.min_vol_ratio_base2 !== undefined) ? `${p.min_vol_ratio_base2.toFixed(2)}x` : '--';
            
            no2RowsHtml += `
                <tr class="hover:bg-slate-800/50 transition cursor-pointer" onclick="openNo2Modal('${p.symbol}')">
                    <td class="p-3 font-extrabold text-white text-sm whitespace-nowrap">
                        <div class="flex items-center gap-1.5">
                            <span class="text-purple-300 font-black">${p.symbol}</span>
                            ${actBadge}
                        </div>
                    </td>
                    <td class="p-3 text-slate-400 text-xs">${sector}</td>
                    <td class="p-3 text-right font-bold text-white">${closeVal}</td>
                    <td class="p-3 text-right font-bold ${chgColor}">${chgVal}</td>
                    <td class="p-3 text-center font-bold text-sky-400">${s1Gain}</td>
                    <td class="p-3 text-center font-mono text-slate-200">${baseLen} <span class="text-[10px] text-slate-400">(-${baseDepth})</span></td>
                    <td class="p-3 text-center font-mono ${p.min_vol_ratio_base2 <= 0.5 ? 'text-emerald-400 font-bold' : 'text-slate-400'}">${minVol}</td>
                    <td class="p-3 text-center font-mono text-sm ${scoreColor}">${p.no2_score ? p.no2_score.toFixed(1) : '--'}/100</td>
                    <td class="p-3 text-center font-mono ${bmsColor}">${p.bms_score ? p.bms_score.toFixed(1) : '--'}</td>
                    <td class="p-3 text-center">
                        <button onclick="event.stopPropagation(); openNo2Modal('${p.symbol}')" class="px-2 py-1 rounded bg-purple-500/20 hover:bg-purple-500/30 text-purple-300 border border-purple-500/40 text-[11px] font-bold transition flex items-center gap-1 mx-auto shadow-sm">
                            <span>🏆</span> <span>6 Tầng</span>
                        </button>
                    </td>
                    <td class="p-3 text-center whitespace-nowrap">
                        <button onclick="event.stopPropagation(); inspectStockFromScreener('${p.symbol}')" class="bg-emerald-600 hover:bg-emerald-500 text-white px-2 py-1 rounded text-[11px] font-bold transition shadow-sm cursor-pointer">
                            Soi Tab 1
                        </button>
                        <button onclick="event.stopPropagation(); quickTrackCurrentStock('${p.symbol}')" class="bg-amber-600 hover:bg-amber-500 text-white px-2 py-1 rounded text-[11px] font-bold transition shadow-sm ml-1 cursor-pointer border border-amber-400/30" title="Đưa cổ phiếu này vào Bot Telegram giám sát">
                            📌 Giám sát
                        </button>
                    </td>
                </tr>
            `;
        });

        container.innerHTML = `
            <table class="w-full text-left text-xs border-collapse">
                <thead>
                    <tr class="bg-slate-900/80 text-purple-300 border-b border-slate-800 text-[11px] uppercase tracking-wider font-extrabold">
                        <th class="p-3">Mã CP &amp; Vị Thế</th>
                        <th class="p-3">Ngành</th>
                        <th class="p-3 text-right">Giá</th>
                        <th class="p-3 text-right">% Chg</th>
                        <th class="p-3 text-center">Nhịp 1</th>
                        <th class="p-3 text-center">Nền Số 2 (Độ nén)</th>
                        <th class="p-3 text-center">Đáy Kiệt Vol</th>
                        <th class="p-3 text-center">Điểm No2</th>
                        <th class="p-3 text-center">Xung Lực BMS</th>
                        <th class="p-3 text-center">Bóc Tách 6 Tầng</th>
                        <th class="p-3 text-center">Hành Động</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-800/60 font-mono">
                    ${no2RowsHtml}
                </tbody>
            </table>
        `;
        return;
    }

    // SPECIAL DEDICATED VIEW FOR SUPER STOCK RADAR
    if (activeScanTier === 'super_stock') {
        let ssRowsHtml = '';
        allItems.forEach(p => {
            const chgColor = p.chg_pct > 0 ? 'text-emerald-400' : (p.chg_pct < 0 ? 'text-rose-400' : 'text-amber-400');
            const chgSign = p.chg_pct >= 0 ? '+' : '';
            const volColor = p.vol_ratio >= 1.8 ? 'text-amber-300 font-bold' : 'text-slate-300';
            const scoreColor = p.super_stock_score >= 85 ? 'text-amber-400 font-black' : (p.super_stock_score >= 70 ? 'text-emerald-400 font-extrabold' : 'text-sky-400 font-bold');
            const badgeBg = p.super_stock_score >= 85 ? 'bg-amber-950/80 text-amber-300 border-amber-500/50' : (p.super_stock_score >= 70 ? 'bg-emerald-950/80 text-emerald-300 border-emerald-500/40' : 'bg-slate-900 text-slate-300 border-slate-700');
            const sector = SECTOR_NAMES[p.symbol] || p.sector || 'Cơ bản';
            
            ssRowsHtml += `
                <tr class="hover:bg-slate-800/50 transition cursor-pointer" onclick="openSuperStockModal('${p.symbol}')">
                    <td class="p-3 font-extrabold text-white text-sm whitespace-nowrap">
                        <div class="flex items-center gap-1.5">
                            <span class="text-amber-400 font-black">${p.symbol}</span>
                            <span class="text-[10px] px-2 py-0.5 rounded-full border ${badgeBg}">${p.tier_badge || 'THEO DÕI'}</span>
                        </div>
                    </td>
                    <td class="p-3 text-slate-400 text-xs">${sector}</td>
                    <td class="p-3 text-right font-bold text-white">${p.close.toFixed(2)}</td>
                    <td class="p-3 text-right font-bold ${chgColor}">${chgSign}${p.chg_pct.toFixed(2)}%</td>
                    <td class="p-3 text-right ${volColor}">${p.vol_ratio.toFixed(2)}x</td>
                    <td class="p-3 text-center font-mono text-sm ${scoreColor}">${p.super_stock_score.toFixed(1)}/100</td>
                    <td class="p-3 text-center font-mono text-emerald-400 font-bold">${p.expected_mfe || '+35% - +60%'}</td>
                    <td class="p-3 text-center">
                        <button onclick="event.stopPropagation(); openSuperStockModal('${p.symbol}')" class="px-2 py-1 rounded bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 text-[11px] font-bold transition flex items-center gap-1 mx-auto shadow-sm">
                            <span>💎</span> <span>5 Trụ Cột</span>
                        </button>
                    </td>
                    <td class="p-3 text-center whitespace-nowrap">
                        <button onclick="event.stopPropagation(); inspectStockFromScreener('${p.symbol}')" class="bg-emerald-600 hover:bg-emerald-500 text-white px-2 py-1 rounded text-[11px] font-bold transition shadow-sm cursor-pointer">
                            Soi Tab 1
                        </button>
                        <button onclick="event.stopPropagation(); quickTrackCurrentStock('${p.symbol}')" class="bg-amber-600 hover:bg-amber-500 text-white px-2 py-1 rounded text-[11px] font-bold transition shadow-sm ml-1 cursor-pointer border border-amber-400/30" title="Đưa cổ phiếu này vào Bot Telegram giám sát">
                            📌 Giám sát
                        </button>
                    </td>
                </tr>
            `;
        });

        container.innerHTML = `
            <table class="w-full text-left text-xs border-collapse">
                <thead>
                    <tr class="bg-slate-900/80 text-amber-300 border-b border-slate-800 text-[11px] uppercase tracking-wider font-extrabold">
                        <th class="p-3">Mã CP &amp; Phân Cấp</th>
                        <th class="p-3">Sóng Ngành</th>
                        <th class="p-3 text-right">Giá</th>
                        <th class="p-3 text-right">% Chg</th>
                        <th class="p-3 text-right">Vol Đột Biến</th>
                        <th class="p-3 text-center">Xác Suất Siêu CP</th>
                        <th class="p-3 text-center">Kỳ Vọng Sóng (MFE)</th>
                        <th class="p-3 text-center">Đánh Giá 5 Trụ Cột</th>
                        <th class="p-3 text-center">Hành Động</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-800/60 font-mono">
                    ${ssRowsHtml}
                </tbody>
            </table>
        `;
        return;
    }

    let rowsHtml = '';
    allItems.forEach(p => {
        const chgColor = p.chg_pct > 0 ? 'text-emerald-400' : (p.chg_pct < 0 ? 'text-rose-400' : 'text-amber-400');
        const chgSign = p.chg_pct >= 0 ? '+' : '';
        const volColor = (p.vol_r10 || p.vol_ratio || 1.0) <= 0.85 ? 'text-emerald-300' : ((p.vol_r10 || p.vol_ratio || 1.0) >= 1.5 ? 'text-amber-300' : 'text-slate-300');
        const volVal = p.vol_r10 || p.vol_ratio || 1.0;
        const volTag = volVal <= 0.85 ? '(Kiệt)' : (volVal >= 1.5 ? '(Đột biến)' : '');
        
        // Tầng VSA badge chuẩn hóa BDI Engine
        let tierBadge = '<span class="tag-pill bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-bold">🟢 C1 Cược Nền</span>';
        if (p.point_code === "P1" || p.desc?.includes("Pocket") || p.desc?.includes("Pivot (P1)")) {
            tierBadge = '<span class="tag-pill bg-amber-500/20 text-amber-400 border border-amber-500/30 font-bold">🟡 P1 Pocket Pivot</span>';
        } else if (p.point_code === "B1" || p.desc?.includes("Breakout") || p.desc?.includes("Nổ") || p.desc?.includes("Surge")) {
            tierBadge = '<span class="tag-pill bg-blue-500/20 text-blue-400 border border-blue-500/30 font-bold">🔵 B1 Breakout</span>';
        }

        const mlProb = p.ml_prob ? `${p.ml_prob}%` : (p.score >= 70 ? '68.5%' : (p.score >= 50 ? '56.2%' : '42.0%'));
        const mlColor = parseFloat(mlProb) >= 60 ? 'text-emerald-400' : (parseFloat(mlProb) >= 50 ? 'text-sky-400' : 'text-slate-400');
        const sector = SECTOR_NAMES[p.symbol] || p.sector || 'Cơ bản';

        const isSurge = Boolean(volVal >= 2.5 || p.is_volume_surge);
        const surgeBadge = isSurge ? '<span class="inline-block px-1.5 py-0.5 rounded text-[10px] font-black bg-rose-950 text-rose-300 border border-rose-500/50 animate-pulse ml-1" title="Khối lượng bùng nổ >= 2.5x TB10">🔥 Vol Surge</span>' : '';

        rowsHtml += `
            <tr class="hover:bg-slate-800/50 transition cursor-pointer" onclick="inspectStockFromScreener('${p.symbol}')">
                <td class="p-3 font-extrabold text-emerald-400 text-sm whitespace-nowrap">${p.symbol} ${surgeBadge}</td>
                <td class="p-3 text-slate-400">${sector}</td>
                <td class="p-3 text-right font-bold text-white">${p.close.toFixed(2)}</td>
                <td class="p-3 text-right font-bold ${chgColor}">${chgSign}${p.chg_pct.toFixed(2)}%</td>
                <td class="p-3 text-right ${volColor}">${volVal.toFixed(2)}x ${volTag}</td>
                <td class="p-3 text-center">${tierBadge}</td>
                <td class="p-3 text-center font-extrabold ${mlColor}">${mlProb}</td>
                <td class="p-3 text-slate-300 max-w-[200px] truncate" title="${p.desc || ''}">${p.desc || 'Tín hiệu VSA'}</td>
                <td class="p-3 text-center whitespace-nowrap">
                    <button onclick="event.stopPropagation(); inspectStockFromScreener('${p.symbol}')" class="bg-emerald-600 hover:bg-emerald-500 text-white px-2 py-1 rounded text-[11px] font-bold transition shadow-sm cursor-pointer">
                        Soi Tab 1
                    </button>
                    <button onclick="event.stopPropagation(); quickTrackCurrentStock('${p.symbol}')" class="bg-amber-600 hover:bg-amber-500 text-white px-2 py-1 rounded text-[11px] font-bold transition shadow-sm ml-1 cursor-pointer border border-amber-400/30" title="Đưa cổ phiếu này vào Bot Telegram giám sát">
                        📌 Giám sát
                    </button>
                </td>
            </tr>
        `;
    });

    container.innerHTML = `
        <table class="w-full text-left text-xs border-collapse">
            <thead>
                <tr class="bg-slate-900/60 text-slate-400 border-b border-slate-800 text-[11px] uppercase tracking-wider">
                    <th class="p-3">Mã CP</th>
                    <th class="p-3">Ngành</th>
                    <th class="p-3 text-right">Giá</th>
                    <th class="p-3 text-right">% Chg</th>
                    <th class="p-3 text-right">Vol/TB10</th>
                    <th class="p-3 text-center">Tầng VSA</th>
                    <th class="p-3 text-center">Xác Suất ML</th>
                    <th class="p-3">Tín Hiệu / Mẫu Hình</th>
                    <th class="p-3 text-center">Hành Động</th>
                </tr>
            </thead>
            <tbody class="divide-y divide-slate-800/60 font-mono">
                ${rowsHtml}
            </tbody>
        </table>
    `;
}


function exportScreenerExcel() {
    if (!currentScanData) {
        alert("Chưa có dữ liệu quét sàn. Vui lòng bấm '⚡ Bắt Đầu Quét' trước!");
        return;
    }
    
    const rows = [
        ["Mã CP", "Tầng Điểm Mua", "Giá Đóng Cửa", "Thay Đổi (%)", "Vol/TB10", "Điểm VSA", "ML Win Rate (%)", "Mô Tả Tín Hiệu"]
    ];
    
    const addItems = (items, tierName) => {
        items.forEach(it => {
            rows.push([
                it.symbol,
                tierName,
                it.close,
                it.chg_pct + "%",
                it.vol_r10 + "x",
                it.score,
                it.ml_prob ? it.ml_prob + "%" : "--",
                `"${(it.desc || '').replace(/"/g, '""')}"`
            ]);
        });
    };
    
    addItems(currentScanData.tier1_cuoc || [], "Tầng 1 (Điểm Cược)");
    addItems(currentScanData.tier2_pocket || [], "Tầng 2 (Đẩy Nền Pocket)");
    addItems(currentScanData.tier3_pivot || [], "Tầng 3 (Pivot/Bùng Nổ)");
    
    const csvContent = "\uFEFF" + rows.map(e => e.join(",")).join("\n");
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `VSA_DauMam_QuetSan_${new Date().toISOString().slice(0,10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// ==================== XUẤT WATCHLIST SANG AMIBROKER (TAB 3) ====================
async function exportToAmiBroker() {
    if (!currentScanData) {
        alert("Chưa có dữ liệu quét thị trường. Vui lòng bấm '⚡ Bắt Đầu Quét' trước!");
        return;
    }
    
    // Thu thập tất cả các mã cổ phiếu từ kết quả quét hiện tại
    const symbolSet = new Set();
    
    // Lấy toàn bộ mã từ tất cả các tầng/radar đã quét
    (currentScanData.tier1_cuoc || []).forEach(it => { if (it.symbol) symbolSet.add(it.symbol.toUpperCase().trim()); });
    (currentScanData.tier2_pocket || []).forEach(it => { if (it.symbol) symbolSet.add(it.symbol.toUpperCase().trim()); });
    (currentScanData.tier3_pivot || []).forEach(it => { if (it.symbol) symbolSet.add(it.symbol.toUpperCase().trim()); });
    (currentScanData.no2 || []).forEach(it => { if (it.symbol) symbolSet.add(it.symbol.toUpperCase().trim()); });
    (currentScanData.super_stock || []).forEach(it => { if (it.symbol) symbolSet.add(it.symbol.toUpperCase().trim()); });
    (currentScanData.ml_picks || []).forEach(it => { if (it.symbol) symbolSet.add(it.symbol.toUpperCase().trim()); });

    const symbols = Array.from(symbolSet);
    if (symbols.length === 0) {
        alert("Không tìm thấy mã nào trong kết quả quét hiện tại để xuất!");
        return;
    }

    try {
        const res = await fetch("/api/export_to_amibroker", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ symbols: symbols, list_name: "VSA_DauMam" })
        });
        const data = await res.json();
        if (data.status === "success") {
            alert(`🎉 CHUYỂN SANG AMIBROKER THÀNH CÔNG!\n\n• Đã nạp: ${data.count} mã cổ phiếu vào Watchlist duy nhất: 'VSA_DauMam'\n• Danh sách cũ trong AmiBroker đã được tự động làm mới hoàn toàn.\n• Vị trí file: C:\\Program Files (x86)\\AmiBroker\\MyNewData\\WatchLists\\VSA_DauMam.tls\n\n👉 Bạn chỉ cần vào AmiBroker -> Chuột phải vào Watch Lists -> Chọn 'Refresh' là xem được ngay!`);
        } else {
            alert("❌ Lỗi chuyển sang AmiBroker: " + (data.message || "Không xác định"));
        }
    } catch (err) {
        alert("❌ Lỗi kết nối máy chủ: " + err);
    }
}
window.exportToAmiBroker = exportToAmiBroker;

// ==================== OPEN STORY TAB ====================
function openStoryTab() {
    const sym = document.getElementById("symbolInput")?.value.trim().toUpperCase() || "TCB";
    const dateVal = document.getElementById("dateInput")?.value || "";
    const url = `/static/story.html?symbol=${encodeURIComponent(sym)}${dateVal ? '&date=' + encodeURIComponent(dateVal) : ''}`;
    window.open(url, '_blank');
}
window.openStoryTab = openStoryTab;

// ==================== DIAGNOSE TAB 2 STOCK ====================
async function diagnoseTab2Stock() {
    const sym = document.getElementById("tab2SymbolInput")?.value.trim().toUpperCase() || "TCB";
    const dateVal = document.getElementById("tab2DateInput")?.value || null;
    const btn = document.getElementById("btnTab2Diagnose");
    const statusBadge = document.getElementById("tab2StatusBadge");
    
    if (btn) btn.innerHTML = "<span>⏳</span> <span>Đang Quét...</span>";
    if (statusBadge) {
        statusBadge.innerText = "⏳ Đang Chạy Quét AI...";
        statusBadge.className = "tag-pill bg-amber-500/20 text-amber-300 border border-amber-500/40 text-xs md:text-sm font-bold";
    }
    
    try {
        const res = await fetch("/api/evaluate", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({symbol: sym, target_date: dateVal})
        });
        if (res.ok) {
            const resJson = await res.json();
            if (resJson.status === "success") {
                window.lastEvaluationResult = {
                    data: resJson.data,
                    aiReasoning: resJson.ai_reasoning,
                    mlPrediction: resJson.ml_prediction,
                    patternMatch: resJson.pattern_match,
                    zeroLossMetrics: resJson.zero_loss_metrics,
                    zeroDinhMetrics: resJson.zero_dinh_metrics
                };
                renderMLAndPatternData(
                    resJson.ml_prediction,
                    resJson.pattern_match,
                    resJson.zero_loss_metrics,
                    resJson.zero_dinh_metrics,
                    resJson.data
                );
                if (resJson.ai_reasoning?.diagnosis) {
                    renderAcademicDiagnosis(resJson.ai_reasoning.diagnosis, resJson.data);
                }
                if (statusBadge) {
                    statusBadge.innerText = `✅ Đã Chẩn Đoán (${sym})`;
                    statusBadge.className = "tag-pill bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 text-xs md:text-sm font-bold";
                }
            } else {
                if (statusBadge) statusBadge.innerText = "❌ Không có dữ liệu";
            }
        }
    } catch (e) {
        console.error("Lỗi chẩn đoán Tab 2:", e);
        if (statusBadge) statusBadge.innerText = "❌ Lỗi kết nối";
    } finally {
        if (btn) btn.innerHTML = "<span>🔬</span> <span>Chẩn Đoán</span>";
    }
}
window.diagnoseTab2Stock = diagnoseTab2Stock;




// ==============================================================================
// TAB 2: HỆ THỐNG CHẤM ĐIỂM BDI (VSA ÔNG BÌNH DESIGN INDEX) & CẢNH BÁO RRBDI
// ==============================================================================
window.currentBdiData = null;

async function calculateBdiScore() {
    const symInput = document.getElementById("bdiSymbolInput");
    const dateInput = document.getElementById("bdiDateInput");
    const symbol = (symInput ? symInput.value : "TCB").toUpperCase().trim();
    const targetDate = dateInput ? dateInput.value : "";
    
    if (!symbol) {
        alert("Vui lòng nhập mã cổ phiếu để chấm điểm BDI!");
        return;
    }

    const btn = document.getElementById("btnBdiScore");
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span>⏳</span> <span>Đang chấm BDI...</span>';
    }

    try {
        const res = await fetch("/api/bdi/score", {
            method: "POST",
            headers: getAuthHeaders(),
            body: JSON.stringify({ symbol: symbol, target_date: targetDate || null })
        });
        
        if (!res.ok) {
            throw new Error(`Lỗi máy chủ (${res.status})`);
        }
        
        const data = await res.json();
        if (data.status === "error") {
            alert(`Lỗi chấm điểm BDI: ${data.message}`);
            return;
        }

        window.currentBdiData = data;
        renderBdiScoreResult(data);

    } catch (err) {
        console.error("Lỗi calculateBdiScore:", err);
        alert(`Không thể chấm điểm BDI cho mã ${symbol}: ${err.message}`);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<span>🎯</span> <span>Chấm Điểm BDI</span>';
        }
    }
}

function renderBdiScoreResult(data) {
    if (!data) return;

    // 1. Thẻ điểm tổng hợp
    const symDisplay = document.getElementById("bdiSymbolDisplay");
    if (symDisplay) symDisplay.innerText = data.symbol;

    const evalDateEl = document.getElementById("bdiEvaluatedDate");
    if (evalDateEl) evalDateEl.innerText = data.date || "--";

    const dateInput = document.getElementById("bdiDateInput");
    if (dateInput && !dateInput.value && data.date) {
        dateInput.value = data.date;
    }

    const scoreVal = document.getElementById("bdiScoreVal");
    if (scoreVal) scoreVal.innerText = data.bdi_score;

    const tierBadge = document.getElementById("bdiTierBadge");
    if (tierBadge) {
        tierBadge.innerText = data.recommendation;
        if (data.bdi_score >= 80) {
            tierBadge.className = "inline-block px-4 py-1.5 rounded-full text-sm font-black bg-emerald-950 text-emerald-300 border border-emerald-500 shadow-lg";
        } else if (data.bdi_score >= 65) {
            tierBadge.className = "inline-block px-4 py-1.5 rounded-full text-sm font-black bg-emerald-950 text-emerald-400 border border-emerald-500/60 shadow-lg";
        } else if (data.bdi_score >= 50) {
            tierBadge.className = "inline-block px-4 py-1.5 rounded-full text-sm font-black bg-amber-950 text-amber-300 border border-amber-500 shadow-lg";
        } else {
            tierBadge.className = "inline-block px-4 py-1.5 rounded-full text-sm font-black bg-rose-950 text-rose-300 border border-rose-500 shadow-lg";
        }
    }

    const pointName = document.getElementById("bdiPointName");
    if (pointName) {
        pointName.innerText = data.point_name;
        if (data.point_code === "B1" || data.point_name?.includes("Breakout")) {
            // Điểm nổ Breakout là màu tím
            pointName.className = "text-lg font-black text-purple-400 mt-1";
        } else if (data.point_code === "P1" || data.point_code === "C1" || data.point_name?.includes("Pivot") || data.point_name?.includes("Cược")) {
            // Các điểm mua là màu xanh lá cây
            pointName.className = "text-lg font-black text-emerald-400 mt-1";
        } else {
            // Cảnh báo là màu vàng với đỏ
            if (data.bdi_score < 50) {
                pointName.className = "text-lg font-black text-rose-400 mt-1";
            } else {
                pointName.className = "text-lg font-black text-amber-400 mt-1";
            }
        }
    }

    // Giá & Dừng lỗ
    const closeEl = document.getElementById("bdiCloseVal");
    if (closeEl) closeEl.innerText = `${data.close.toLocaleString()} VNĐ`;

    const chgEl = document.getElementById("bdiChgVal");
    if (chgEl) {
        chgEl.innerText = `${data.chg_pct > 0 ? '+' : ''}${data.chg_pct}%`;
        chgEl.className = data.chg_pct >= 0 ? "text-xs text-emerald-400 font-bold block" : "text-xs text-rose-400 font-bold block";
    }

    const lowEl = document.getElementById("bdiLowVal");
    if (lowEl) lowEl.innerText = `${data.low_buy.toLocaleString()} VNĐ`;

    // Tự động điền Giá mua vào ô nhập trước khi bấm Xác nhận mua
    const buyPriceInp = document.getElementById("bdiBuyPriceInput");
    if (buyPriceInp) {
        buyPriceInp.value = data.close;
    }

    const riskEl = document.getElementById("bdiRiskPct");
    if (riskEl) {
        const riskPct = ((data.close - data.low_buy) / data.close * 100);
        riskEl.innerText = `Khoảng cách cắt lỗ: -${riskPct.toFixed(1)}%`;
    }

    // Advice Box
    const adviceEl = document.getElementById("bdiAdviceBox");
    if (adviceEl) {
        let adviceHtml = `💡 <strong>Đánh giá thực chiến:</strong> `;
        if (data.bdi_score >= 80) {
            adviceHtml += `Hội tụ tối đa 8 tiêu chí (${data.bdi_score}/100đ). Xác suất thắng lịch sử đạt <strong>${data.winrate_est}%</strong>. Điểm mua <strong>${data.point_name}</strong> rất an toàn, khuyến nghị giải ngân quyết đoán theo quy tắc phân bổ vốn 4x2!`;
        } else if (data.bdi_score >= 65) {
            adviceHtml += `Đạt tiêu chuẩn mua chuẩn (${data.bdi_score}/100đ, xác suất thắng <strong>${data.winrate_est}%</strong>). Có thể giải ngân tỷ trọng 12.5% tiền mặt tại <strong>${data.point_name}</strong> và chờ tín hiệu gia tăng.`;
        } else if (data.bdi_score >= 50) {
            adviceHtml += `Vùng thăm dò (${data.bdi_score}/100đ, xác suất thắng <strong>${data.winrate_est}%</strong>). Một số tiêu chí quan trọng chưa đồng thuận. Chỉ mở mua thăm dò tỷ trọng nhỏ 1/8 và tuân thủ kỷ luật cắt lỗ tuyệt đối!`;
        } else {
            adviceHtml += `CẢNH BÁO RỦI RO (${data.bdi_score}/100đ, xác suất thắng chỉ <strong>${data.winrate_est}%</strong>). Vi phạm nhiều tiêu chí cốt lõi (MACD âm hoặc chưa có dòng tiền bảo trợ). Khuyến nghị <strong>ĐỨNG NGOÀI</strong>, không mở mua mới!`;
        }
        adviceEl.innerHTML = adviceHtml;
    }

    // 2. Bảng 8 Tiêu chí
    const passCount = (data.criteria || []).filter(c => c.passed).length;
    const countBadge = document.getElementById("bdiPassCountBadge");
    if (countBadge) {
        countBadge.innerText = `${passCount}/8 Tiêu Chí Đạt (${data.bdi_score}/100đ)`;
        countBadge.className = passCount >= 6 ? "tag-pill bg-emerald-500/25 text-emerald-300 border border-emerald-500/40 text-xs md:text-sm font-bold" : "tag-pill bg-amber-500/25 text-amber-300 border border-amber-500/40 text-xs md:text-sm font-bold";
    }

    const critListEl = document.getElementById("bdiCriteriaList");
    if (critListEl && data.criteria) {
        critListEl.innerHTML = data.criteria.map(c => {
            const pass = c.passed;
            return `
                <div class="p-3 rounded-xl border ${pass ? 'bg-emerald-950/20 border-emerald-500/40' : 'bg-slate-900 border-slate-800'} flex items-center justify-between gap-3">
                    <div class="flex items-start gap-2.5 flex-1">
                        <span class="text-base">${pass ? '✅' : '❌'}</span>
                        <div>
                            <div class="font-bold ${pass ? 'text-emerald-300' : 'text-slate-300'}">${c.name}</div>
                            <div class="text-[11px] text-slate-400 mt-0.5">${c.desc}</div>
                        </div>
                    </div>
                    <div class="text-right">
                        <span class="text-sm font-black ${pass ? 'text-emerald-400' : 'text-slate-500'} font-mono">${c.points}/${c.max_points}đ</span>
                    </div>
                </div>
            `;
        }).join("");
    }
}

async function confirmBuyPosition() {
    if (!window.currentBdiData) {
        alert("Vui lòng thực hiện chấm điểm BDI trước khi xác nhận mua!");
        return;
    }

    const data = window.currentBdiData;
    const buyPriceInp = document.getElementById("bdiBuyPriceInput");
    const buySharesInp = document.getElementById("bdiBuySharesInput");

    const buyPrice = (buyPriceInp && parseFloat(buyPriceInp.value)) ? parseFloat(buyPriceInp.value) : data.close;
    const sharesCount = (buySharesInp && parseInt(buySharesInp.value)) ? parseInt(buySharesInp.value) : 10000;
    const totalEstValue = buyPrice * sharesCount;

    const confirmMsg = `XÁC NHẬN VÀO LỆNH THEO HỆ THỐNG BDI:\n\n` +
        `• Mã CP: ${data.symbol}\n` +
        `• Ngày mua: ${data.date}\n` +
        `• Giá mua: ${buyPrice.toLocaleString()} VNĐ\n` +
        `• Số lượng: ${sharesCount.toLocaleString()} CP\n` +
        `• Tổng giá trị: ${(totalEstValue).toLocaleString()} VNĐ\n` +
        `• Điểm mua: ${data.point_name}\n` +
        `• Điểm BDI: ${data.bdi_score}/100đ (${data.recommendation})\n` +
        `• Giá cắt lỗ cứng (Low nến): ${data.low_buy.toLocaleString()} VNĐ\n\n` +
        `Bạn có chắc chắn muốn lưu vị thế này để hệ thống RRBDI theo dõi và cảnh báo rủi ro?`;

    if (!confirm(confirmMsg)) return;

    try {
        const res = await fetch("/api/bdi/buy", {
            method: "POST",
            headers: getAuthHeaders(),
            body: JSON.stringify({
                symbol: data.symbol,
                buy_date: data.date,
                buy_price: buyPrice,
                low_price: data.low_buy,
                shares_count: sharesCount,
                point_name: data.point_name,
                bdi_score: data.bdi_score,
                notes: `BDI Score: ${data.bdi_score}`
            })
        });

        if (!res.ok) throw new Error(`Lỗi máy chủ (${res.status})`);
        const resData = await res.json();
        
        alert(`🎉 Đã lưu vị thế mua ${data.symbol} (${sharesCount.toLocaleString()} CP @ ${buyPrice.toLocaleString()} VNĐ) thành công!\nHệ thống RRBDI đã bắt đầu giám sát chu kỳ và cảnh báo tự động.`);
        loadTrackedPositions();

    } catch (err) {
        console.error("Lỗi confirmBuyPosition:", err);
        alert(`Không thể lưu vị thế mua: ${err.message}`);
    }
}

async function loadTrackedPositions() {
    const tbody = document.getElementById("trackedPositionsTableBody");
    const countBadge = document.getElementById("trackedCountBadge");
    const headerTrackedCount = document.getElementById("headerTrackedCount");
    const headerTotalPnl = document.getElementById("headerTotalPnl");
    
    try {
        const res = await fetch("/api/bdi/tracked", {
            headers: getAuthHeaders()
        });
        if (!res.ok) return;
        
        const resData = await res.json();
        const positions = resData.data || [];
        
        if (countBadge) countBadge.innerText = positions.length;

        // Tính toán tổng vốn đầu tư, tổng giá trị hiện tại và tỉ lệ lãi/lỗ danh mục
        let totalCost = 0;
        let totalCurrentVal = 0;
        let totalShares = 0;

        positions.forEach(pos => {
            const shares = parseInt(pos.shares_count || pos.shares || 10000);
            const buyPrice = parseFloat(pos.buy_price || 0);
            const curPrice = parseFloat(pos.current_price !== undefined ? pos.current_price : buyPrice);
            
            const cost = buyPrice * shares;
            const curVal = curPrice * shares;

            totalCost += cost;
            totalCurrentVal += curVal;
            totalShares += shares;
        });

        const totalPnlPct = totalCost > 0 ? ((totalCurrentVal - totalCost) / totalCost * 100) : 0;

        // Cập nhật thống kê trên thanh tiêu đề Tab 2: Số lượng CP đang nắm giữ & Tỉ lệ Lãi/Lỗ
        if (headerTrackedCount) {
            headerTrackedCount.innerHTML = `${positions.length} mã <span class="text-xs font-normal text-slate-400">(${totalShares.toLocaleString()} CP)</span>`;
        }

        if (headerTotalPnl) {
            const pPrefix = totalPnlPct > 0 ? "+" : "";
            headerTotalPnl.innerText = `${pPrefix}${totalPnlPct.toFixed(2)}%`;
            if (totalPnlPct >= 0) {
                headerTotalPnl.className = "font-mono font-black text-sm md:text-base text-emerald-400";
            } else {
                headerTotalPnl.className = "font-mono font-black text-sm md:text-base text-rose-400";
            }
        }

        if (!tbody) return;

        if (positions.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="10" class="p-8 text-center text-slate-400">
                        <div class="text-3xl mb-2">📥</div>
                        <div>Chưa có vị thế mua nào được theo dõi.</div>
                        <div class="text-xs text-slate-500 mt-1">Hãy nhập mã cổ phiếu ở trên, nhấn "🎯 Chấm Điểm BDI" và "✅ Xác Nhận Mua" để đưa vào hệ thống kiểm soát RRBDI.</div>
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = positions.map(pos => {
            const shares = parseInt(pos.shares_count || pos.shares || 10000);
            const buyPrice = parseFloat(pos.buy_price || 0);
            const curPrice = parseFloat(pos.current_price !== undefined ? pos.current_price : buyPrice);
            const costVal = buyPrice * shares;
            const curVal = curPrice * shares;
            const profitAmt = curVal - costVal;

            const pPct = pos.profit_pct !== undefined ? pos.profit_pct : (buyPrice > 0 ? ((curPrice - buyPrice) / buyPrice * 100) : 0);
            const pClass = pPct >= 0 ? "text-emerald-400 font-bold" : "text-rose-400 font-bold";
            const pPrefix = pPct > 0 ? "+" : "";

            // Tỉ trọng % NAV tổng danh mục
            const navWeight = totalCurrentVal > 0 ? ((curVal / totalCurrentVal) * 100) : 0;

            let rrbdiBadgeHtml = "";
            if (pos.rrbdi_level === "RED") {
                rrbdiBadgeHtml = `<span class="px-2 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-500 font-extrabold text-[11px] block w-fit mb-1">🚨 CẤP 3: CẮT LỖ 100%</span>`;
            } else if (pos.rrbdi_level === "ORANGE") {
                rrbdiBadgeHtml = `<span class="px-2 py-0.5 rounded bg-orange-950 text-orange-300 border border-orange-500 font-bold text-[11px] block w-fit mb-1">🟠 CẤP 2: HẠ 50%</span>`;
            } else if (pos.rrbdi_level === "YELLOW") {
                rrbdiBadgeHtml = `<span class="px-2 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-500 font-bold text-[11px] block w-fit mb-1">🟡 CẤP 1: CẢNH BÁO VÀNG</span>`;
            } else {
                rrbdiBadgeHtml = `<span class="px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-500/50 font-bold text-[11px] block w-fit mb-1">🟢 AN TOÀN</span>`;
            }

            let nextBuyHtml = "";
            if (pos.next_buy_signal) {
                nextBuyHtml = `
                    <div class="p-2 bg-emerald-950/40 border border-emerald-500/50 rounded-lg text-emerald-300 text-xs font-bold mb-1.5 flex items-center justify-between gap-2">
                        <span>${pos.next_buy_signal}</span>
                        <button onclick="quickAddOnBuy('${pos.symbol}')" class="px-2 py-1 bg-emerald-600 hover:bg-emerald-500 text-white rounded font-bold text-[11px] cursor-pointer whitespace-nowrap">MUA GIA TĂNG</button>
                    </div>
                `;
            }

            let pointBadgeClass = "bg-slate-800 text-slate-300";
            if (pos.point_name?.includes("Breakout") || pos.point_name?.includes("B1")) {
                pointBadgeClass = "bg-purple-950 text-purple-300 border border-purple-500/50";
            } else if (pos.point_name?.includes("Pivot") || pos.point_name?.includes("P1") || pos.point_name?.includes("Cược") || pos.point_name?.includes("C1")) {
                pointBadgeClass = "bg-emerald-950 text-emerald-300 border border-emerald-500/50";
            } else {
                pointBadgeClass = "bg-amber-950 text-amber-300 border border-amber-500/50";
            }

            return `
                <tr class="hover:bg-slate-800/40 transition">
                    <td class="p-3">
                        <strong class="text-white text-base font-black font-mono block">${pos.symbol}</strong>
                        <span class="text-[11px] text-slate-400">${pos.sector || 'Sàn HOSE'}</span>
                    </td>
                    <td class="p-3">
                        <div class="text-white font-bold font-mono">${buyPrice.toLocaleString()}</div>
                        <div class="text-[11px] text-slate-400">${pos.buy_date}</div>
                        <div class="text-[10px] text-rose-400 font-mono">Low: ${pos.buy_low ? pos.buy_low.toLocaleString() : (pos.low_price ? pos.low_price.toLocaleString() : '--')}</div>
                    </td>
                    <td class="p-3">
                        <div class="text-white font-bold font-mono">${shares.toLocaleString()} <span class="text-[10px] text-slate-400 font-normal">CP</span></div>
                        <div class="text-[10px] text-slate-400 font-mono">${(costVal).toLocaleString()} đ</div>
                    </td>
                    <td class="p-3">
                        <span class="px-2 py-0.5 rounded-lg bg-sky-950/70 text-sky-300 border border-sky-500/40 font-mono font-bold text-xs">${navWeight.toFixed(1)}%</span>
                        <div class="text-[10px] text-slate-400 mt-0.5 font-mono">${(curVal).toLocaleString()} đ</div>
                    </td>
                    <td class="p-3">
                        <span class="px-2.5 py-1 rounded-lg text-xs font-black ${pointBadgeClass}">${pos.point_name || 'VSA'}</span>
                    </td>
                    <td class="p-3">
                        <span class="text-white font-bold text-sm font-mono">${curPrice.toLocaleString()}</span>
                    </td>
                    <td class="p-3">
                        <span class="${pClass} text-sm font-mono">${pPrefix}${pPct.toFixed(2)}%</span>
                        <div class="text-[10px] ${profitAmt >= 0 ? 'text-emerald-400' : 'text-rose-400'} font-mono">${profitAmt >= 0 ? '+' : ''}${Math.round(profitAmt).toLocaleString()} đ</div>
                    </td>
                    <td class="p-3">
                        <strong class="text-emerald-400 font-mono text-sm">${pos.current_bdi || pos.initial_bdi || '--'}/100</strong>
                    </td>
                    <td class="p-3 max-w-md">
                        ${nextBuyHtml}
                        ${rrbdiBadgeHtml}
                        <div class="text-[11px] text-slate-300 leading-snug">${pos.rrbdi_alert || 'Bình thường'}</div>
                    </td>
                    <td class="p-3 text-center">
                        <button onclick="deleteTrackedPosition('${pos.id}')" class="p-2 bg-rose-950 hover:bg-rose-900 text-rose-300 border border-rose-500/40 rounded-lg text-xs font-bold transition cursor-pointer" title="Tất toán / Xóa vị thế này">
                            🗑️
                        </button>
                    </td>
                </tr>
            `;
        }).join("");

    } catch (err) {
        console.error("Lỗi loadTrackedPositions:", err);
    }
}

async function quickAddOnBuy(symbol) {
    const symInput = document.getElementById("bdiSymbolInput");
    if (symInput) symInput.value = symbol;
    await calculateBdiScore();
    confirmBuyPosition();
}

async function deleteTrackedPosition(posId) {
    if (!confirm("Bạn có chắc chắn muốn tất toán / xóa vị thế này khỏi danh mục theo dõi?")) return;
    
    try {
        const res = await fetch(`/api/bdi/tracked/${posId}`, {
            method: "DELETE",
            headers: getAuthHeaders()
        });
        if (!res.ok) throw new Error(`Lỗi máy chủ (${res.status})`);
        loadTrackedPositions();
    } catch (err) {
        console.error("Lỗi deleteTrackedPosition:", err);
        alert(`Không thể xóa vị thế: ${err.message}`);
    }
}

async function quickTrackCurrentStock(symOverride) {
    const symInput = document.getElementById("symbolInput");
    const sym = (symOverride || (symInput ? symInput.value : "")).trim().toUpperCase();
    if (!sym) {
        alert("Vui lòng nhập mã cổ phiếu!");
        return;
    }
    
    try {
        const res = await fetch("/api/bdi/quick_track", {
            method: "POST",
            headers: getAuthHeaders(),
            body: JSON.stringify({ symbol: sym, notes: "Lưu theo dõi Bot" })
        });
        const resData = await res.json();
        if (resData.status === "success" || resData.status === "exists") {
            alert(`🎉 ${resData.message || 'Đã thêm mã ' + sym + ' vào Danh Sách Theo Dõi (Radar)!'}\nBot sẽ bám sát 30 phút/lần trong phiên để tự động cảnh báo điểm mua mới.`);
            if (typeof loadTrackedPositions === 'function') {
                loadTrackedPositions();
            }
            if (typeof loadWatchlistPositions === 'function') {
                loadWatchlistPositions();
            }
        } else {
            alert(`⚠️ Thông báo: ${resData.message || 'Không thể lưu vị thế'}`);
        }
    } catch (err) {
        console.error("Lỗi quickTrackCurrentStock:", err);
        alert(`Không thể kết nối máy chủ: ${err.message}`);
    }
}

// ==============================================================================
// WATCHLIST RADAR (DANH SÁCH THEO DÕI TỰ ĐỘNG BẮT ĐIỂM MUA)
// ==============================================================================
async function loadWatchlistPositions() {
    const tbody = document.getElementById("watchlistTableBody");
    const countBadge = document.getElementById("watchlistCountBadge");
    
    try {
        const res = await fetch("/api/bdi/watchlist", {
            headers: getAuthHeaders()
        });
        if (!res.ok) return;
        
        const resData = await res.json();
        const watchlist = resData.data || [];
        
        if (countBadge) countBadge.innerText = `${watchlist.length} mã`;
        
        if (!tbody) return;
        
        if (watchlist.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="9" class="p-8 text-center text-slate-400">
                        <div class="text-3xl mb-2">📡</div>
                        <div>Chưa có mã nào trong Danh Sách Theo Dõi (Watchlist Radar).</div>
                        <div class="text-xs text-slate-500 mt-1">Hãy bấm nút "📌 Lưu Giám Sát" ở Tab 1/Tab 3 hoặc nhập mã ở ô "+ Thêm Radar" phía trên để hệ thống tự động bám sát và báo điểm nổ.</div>
                    </td>
                </tr>
            `;
            return;
        }
        
        tbody.innerHTML = watchlist.map(item => {
            const curPrice = parseFloat(item.current_price || 0);
            const addedPrice = parseFloat(item.added_price || curPrice);
            const chgPct = parseFloat(item.today_chg_pct !== undefined ? item.today_chg_pct : 0);
            const volR10 = parseFloat(item.vol_r10 || 1.0);
            const bdi = parseInt(item.current_bdi || item.initial_bdi || 50);
            
            const chgColor = chgPct > 0 ? "text-emerald-400 font-bold" : (chgPct < 0 ? "text-rose-400 font-bold" : "text-amber-400 font-bold");
            const chgPrefix = chgPct > 0 ? "+" : "";
            
            const volColor = volR10 >= 2.5 ? "text-rose-400 font-black animate-pulse" : (volR10 >= 1.5 ? "text-amber-300 font-bold" : (volR10 <= 0.85 ? "text-emerald-300 font-medium" : "text-slate-300"));
            
            // Badge tín hiệu radar
            let signalBadgeClass = "bg-slate-800 text-slate-300 border-slate-700";
            if (item.is_volume_surge || item.signal_badge?.includes("SURGE")) {
                signalBadgeClass = "bg-rose-950 text-rose-300 border-rose-500 font-black animate-pulse";
            } else if (item.point_code === "B1" || item.signal_badge?.includes("BREAKOUT")) {
                signalBadgeClass = "bg-purple-950 text-purple-300 border-purple-500 font-bold";
            } else if (item.point_code === "P1" || item.signal_badge?.includes("PIVOT")) {
                signalBadgeClass = "bg-sky-950 text-sky-300 border-sky-500 font-bold";
            } else if (item.point_code === "C1" || item.signal_badge?.includes("CƯỢC")) {
                signalBadgeClass = "bg-emerald-950 text-emerald-300 border-emerald-500 font-bold";
            } else if (bdi >= 70) {
                signalBadgeClass = "bg-emerald-950/60 text-emerald-400 border-emerald-500/40";
            }

            return `
                <tr class="hover:bg-slate-800/40 transition">
                    <td class="p-3">
                        <strong class="text-amber-400 text-base font-black font-mono block cursor-pointer hover:underline" onclick="inspectStockFromScreener('${item.symbol}')">${item.symbol}</strong>
                        <span class="text-[11px] text-slate-400">${item.sector || 'Sàn HOSE'}</span>
                    </td>
                    <td class="p-3">
                        <div class="text-slate-300 font-medium">${item.added_date || '--'}</div>
                        <div class="text-[11px] text-slate-500 font-mono">Giá theo dõi: ${addedPrice.toLocaleString()}</div>
                    </td>
                    <td class="p-3 text-right">
                        <span class="text-white font-bold text-sm font-mono">${curPrice.toLocaleString()}</span>
                    </td>
                    <td class="p-3 text-right">
                        <span class="${chgColor} text-sm font-mono">${chgPrefix}${chgPct.toFixed(2)}%</span>
                    </td>
                    <td class="p-3 text-right font-mono ${volColor}">
                        ${volR10.toFixed(2)}x
                    </td>
                    <td class="p-3 text-center">
                        <strong class="${bdi >= 70 ? 'text-emerald-400' : (bdi >= 50 ? 'text-amber-400' : 'text-rose-400')} font-mono text-sm">${bdi}/100</strong>
                    </td>
                    <td class="p-3">
                        <span class="px-2.5 py-1 rounded-lg text-xs border ${signalBadgeClass}">
                            ${item.signal_badge || '⚪ Chờ tín hiệu'}
                        </span>
                    </td>
                    <td class="p-3 max-w-sm">
                        <div class="text-xs text-slate-200 font-medium">${item.action_advice || 'Quan sát siết nền'}</div>
                        <div class="text-[10px] text-slate-400 mt-0.5 italic">${item.notes || ''}</div>
                    </td>
                    <td class="p-3 text-center whitespace-nowrap">
                        <button onclick="convertWatchlistToBuy('${item.symbol}', ${curPrice})" class="px-2.5 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-bold transition cursor-pointer shadow-sm mr-1" title="Kích hoạt Mua - Chuyển sang Bảng 1: Danh Mục Nắm Giữ & Quản Trị Vốn RRBDI">
                            ✅ Mở Mua
                        </button>
                        <button onclick="deleteWatchlistPosition('${item.id || item.symbol}')" class="p-1.5 bg-rose-950 hover:bg-rose-900 text-rose-300 border border-rose-500/40 rounded-lg text-xs font-bold transition cursor-pointer" title="Xóa khỏi danh sách theo dõi">
                            🗑️
                        </button>
                    </td>
                </tr>
            `;
        }).join("");
        
    } catch (err) {
        console.error("Lỗi loadWatchlistPositions:", err);
    }
}

async function addStockToWatchlist() {
    const input = document.getElementById("addWatchlistInput");
    const sym = (input ? input.value : "").trim().toUpperCase();
    if (!sym) {
        alert("Vui lòng nhập mã cổ phiếu cần theo dõi!");
        return;
    }
    
    try {
        const res = await fetch("/api/bdi/watchlist", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                ...getAuthHeaders()
            },
            body: JSON.stringify({ symbol: sym, notes: "Thêm thủ công vào Radar" })
        });
        const resData = await res.json();
        if (resData.status === "success" || resData.status === "exists") {
            alert(`🎉 ${resData.message || 'Đã thêm mã ' + sym + ' vào Danh Sách Theo Dõi!'}`);
            if (input) input.value = "";
            loadWatchlistPositions();
        } else {
            alert(`⚠️ Thông báo: ${resData.message || 'Không thể lưu'}`);
        }
    } catch (err) {
        console.error("Lỗi addStockToWatchlist:", err);
        alert(`Không thể kết nối máy chủ: ${err.message}`);
    }
}

async function deleteWatchlistPosition(watchId) {
    if (!confirm("Bạn có chắc chắn muốn xóa mã này khỏi Danh Sách Theo Dõi?")) return;
    
    try {
        const res = await fetch(`/api/bdi/watchlist/${watchId}`, {
            method: "DELETE",
            headers: getAuthHeaders()
        });
        if (!res.ok) throw new Error(`Lỗi máy chủ (${res.status})`);
        loadWatchlistPositions();
    } catch (err) {
        console.error("Lỗi deleteWatchlistPosition:", err);
        alert(`Không thể xóa khỏi danh sách theo dõi: ${err.message}`);
    }
}

async function convertWatchlistToBuy(symbol, defaultPrice) {
    const sharesStr = prompt(`XÁC NHẬN MỞ MUA [${symbol}] TỪ WATCHLIST:\n\nNhập số lượng cổ phiếu muốn mua (mặc định 10,000 CP):`, "10000");
    if (sharesStr === null) return;
    const sharesCount = parseInt(sharesStr) || 10000;
    
    const priceStr = prompt(`Nhập giá khớp lệnh cho [${symbol}] (VNĐ):`, defaultPrice || "");
    if (priceStr === null) return;
    const buyPrice = parseFloat(priceStr) || defaultPrice;
    
    try {
        const res = await fetch("/api/bdi/watchlist/convert_to_buy", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                ...getAuthHeaders()
            },
            body: JSON.stringify({
                symbol: symbol,
                buy_price: buyPrice,
                shares_count: sharesCount,
                notes: `Mở mua kích hoạt từ Watchlist Radar`
            })
        });
        const resData = await res.json();
        if (resData.status === "success") {
            alert(`🎉 KÍCH HOẠT THÀNH CÔNG!\n\nMã ${symbol} đã được mở vị thế mua và CHUYỂN SANG BẢNG 1: DANH MỤC NẮM GIỮ & QUẢN TRỊ VỐN RRBDI để tự động bám sát chu kỳ và bảo vệ tài khoản.`);
            loadTrackedPositions();
            loadWatchlistPositions();
        } else {
            alert(`⚠️ Lỗi: ${resData.message}`);
        }
    } catch (err) {
        console.error("Lỗi convertWatchlistToBuy:", err);
        alert(`Không thể thực hiện chuyển đổi: ${err.message}`);
    }
}

window.quickTrackCurrentStock = quickTrackCurrentStock;
window.calculateBdiScore = calculateBdiScore;
window.confirmBuyPosition = confirmBuyPosition;
window.loadTrackedPositions = loadTrackedPositions;
window.loadWatchlistPositions = loadWatchlistPositions;
window.addStockToWatchlist = addStockToWatchlist;
window.deleteWatchlistPosition = deleteWatchlistPosition;
window.convertWatchlistToBuy = convertWatchlistToBuy;
window.quickAddOnBuy = quickAddOnBuy;
window.deleteTrackedPosition = deleteTrackedPosition;

// ==============================================================================
// TELEGRAM BOT CONFIGURATION HANDLERS
// ==============================================================================
function toggleTelegramConfigPanel() {
    const p = document.getElementById("telegramConfigPanel");
    if (!p) return;
    if (p.style.display === "none" || p.classList.contains("hidden")) {
        p.style.display = "block";
        p.classList.remove("hidden");
        loadTelegramConfigIntoUI();
    } else {
        p.style.display = "none";
        p.classList.add("hidden");
    }
}

async function loadTelegramConfigIntoUI() {
    try {
        const res = await fetch("/api/telegram/config", { headers: getAuthHeaders() });
        if (!res.ok) return;
        const j = await res.json();
        if (j.status === "success" && j.data) {
            const tokenInput = document.getElementById("tgBotTokenInput");
            const chatInput = document.getElementById("tgChatIdInput");
            const enabledCb = document.getElementById("tgEnabledCheckbox");
            if (tokenInput) tokenInput.value = j.data.bot_token || "";
            if (chatInput) chatInput.value = j.data.chat_id || "";
            if (enabledCb) enabledCb.checked = (j.data.enabled !== false);
        }
    } catch (e) {
        console.error("Lỗi loadTelegramConfig:", e);
    }
}

async function saveTelegramConfig() {
    const token = document.getElementById("tgBotTokenInput")?.value?.trim() || "";
    const chatId = document.getElementById("tgChatIdInput")?.value?.trim() || "";
    const enabled = document.getElementById("tgEnabledCheckbox")?.checked ?? true;
    
    try {
        const res = await fetch("/api/telegram/config", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                ...getAuthHeaders()
            },
            body: JSON.stringify({ bot_token: token, chat_id: chatId, enabled: enabled })
        });
        const j = await res.json();
        if (j.status === "success") {
            alert("💾 Đã lưu cấu hình Bot Telegram thành công!\nHệ thống sẵn sàng kích hoạt lịch giám sát tự động.");
        } else {
            alert(`Lỗi: ${j.message}`);
        }
    } catch (e) {
        alert(`Lỗi kết nối: ${e.message}`);
    }
}

async function testTelegramAlert() {
    try {
        const res = await fetch("/api/telegram/test", {
            method: "POST",
            headers: getAuthHeaders()
        });
        const j = await res.json();
        alert(j.message);
    } catch (e) {
        alert(`Lỗi gửi tin: ${e.message}`);
    }
}

window.toggleTelegramConfigPanel = toggleTelegramConfigPanel;
window.saveTelegramConfig = saveTelegramConfig;
window.testTelegramAlert = testTelegramAlert;
