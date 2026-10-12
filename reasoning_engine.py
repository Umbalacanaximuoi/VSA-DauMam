import os
import sys
import glob
import json
import pandas as pd
from datetime import datetime
try:
    from evaluator import evaluate_stock, evaluate_sector_wave, get_sector_peers, safe_print
except ImportError:
    from api.evaluator import evaluate_stock, evaluate_sector_wave, get_sector_peers, safe_print

class KnowledgeManager:
    """
    Manages loading and indexing knowledge base markdown documents.
    """
    def __init__(self, kb_dir=None):
        if kb_dir is None:
            if getattr(sys, 'frozen', False):
                base_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
            else:
                base_dir = os.path.dirname(os.path.abspath(__file__))
            self.kb_dir = os.path.join(base_dir, "knowledge_base")
            if not os.path.exists(self.kb_dir):
                self.kb_dir = os.path.join(os.path.dirname(base_dir), "knowledge_base")
            self.hub_dir = os.path.join(base_dir, "tai_lieu_hoc_may_vsa")
        else:
            self.kb_dir = kb_dir
            self.hub_dir = None

    def list_knowledge(self):
        """
        Returns list of knowledge files and their metadata.
        """
        docs = []
        scan_dirs = [self.kb_dir]
        if hasattr(self, 'hub_dir') and self.hub_dir and os.path.exists(self.hub_dir):
            scan_dirs.append(self.hub_dir)
            for sub in os.listdir(self.hub_dir):
                sub_p = os.path.join(self.hub_dir, sub)
                if os.path.isdir(sub_p):
                    scan_dirs.append(sub_p)

        seen_files = set()
        for sdir in scan_dirs:
            if not os.path.exists(sdir):
                continue
            for fpath in sorted(glob.glob(os.path.join(sdir, "*.*"))):
                if fpath.endswith((".md", ".txt")):
                    fname = os.path.basename(fpath)
                    if fname in seen_files:
                        continue
                    seen_files.add(fname)
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            lines = [line.strip() for line in f.readlines() if line.strip()]
                            title = lines[0].lstrip("#").strip() if lines else fname
                            summary = lines[1].strip() if len(lines) > 1 else ""
                        docs.append({
                            "filename": fname,
                            "path": fpath,
                            "title": title,
                            "summary": summary,
                            "size_kb": round(os.path.getsize(fpath) / 1024, 1)
                        })
                    except Exception:
                        pass
        return docs

    def get_case_studies_summary(self):
        """
        Scans knowledge base for case study files and returns their titles/topics.
        """
        case_files = []
        if not os.path.exists(self.kb_dir):
            return case_files

        for fpath in sorted(glob.glob(os.path.join(self.kb_dir, "*.*"))):
            if fpath.endswith(".md") or fpath.endswith(".txt"):
                fname = os.path.basename(fpath).lower()
                if any(k in fname for k in ["mau_hinh", "case", "thanh_cong", "that_bai", "nhan_dien", "song_nganh", "xung_luc"]):
                    case_files.append(os.path.basename(fpath))
        return case_files

    def get_full_knowledge_text(self):
        """
        Concatenates all knowledge base files into a consolidated text.
        """
        if not os.path.exists(self.kb_dir):
            return ""
        
        full_text = []
        for fpath in sorted(glob.glob(os.path.join(self.kb_dir, "*.*"))):
            if fpath.endswith(".md") or fpath.endswith(".txt"):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        full_text.append(f"--- TÀI LIỆU: {os.path.basename(fpath)} ---\n" + f.read())
                except Exception:
                    pass
        return "\n\n".join(full_text)

class ReasoningEngine:
    """
    Cognitive Reasoning Engine combining quantitative VSA metrics,
    sector wave contexts, and knowledge base rules.
    """
    def __init__(self):
        self.km = KnowledgeManager()

    def diagnose_stock(self, symbol, target_date_str: str = None) -> dict:
        if isinstance(symbol, dict):
            stock_eval = symbol
            symbol = stock_eval.get("symbol", "").upper().strip()
        else:
            symbol = str(symbol).upper().strip()
            stock_eval = evaluate_stock(symbol, target_date_str)
            
        if "error" in stock_eval:
            return {"error": stock_eval["error"]}

        # 2. Get Sector Wave Context
        sector_name, peers = get_sector_peers(symbol)
        sector_wave = None
        if sector_name != "Khác" and len(peers) > 1:
            sector_wave = evaluate_sector_wave(symbol, target_date_str)
            
        # 3. Analyze quantitative indicators
        ind = stock_eval.get("indicators", {})
        price = stock_eval.get("latest_price", 0.0)
        pct_change = stock_eval.get("price_change_pct", 0.0)
        vsa_score = stock_eval.get("score", 0.0)
        rec_status = stock_eval.get("recommendation_status", "")
        rec_desc = stock_eval.get("recommendation_desc", "")
        
        ma10 = ind.get("ma10", 0.0) or 0.0
        ma20 = ind.get("ma20", 0.0) or 0.0
        ma50 = ind.get("ma50", 0.0) or 0.0
        ma200 = ind.get("ma200", 0.0) or 0.0
        vol = ind.get("volume", 0) or 0
        avg_vol10 = ind.get("avg_vol10", 0) or 0
        vol_ratio = (vol / avg_vol10) if (avg_vol10 and avg_vol10 > 0) else ind.get("volume_ratio", 1.0)
        if vol_ratio is None or vol_ratio == 0:
            vol_ratio = 1.0
            
        rsi = ind.get("rsi", 50.0) or 50.0
        macd = ind.get("macd", 0.0) or 0.0
        macd_sig = ind.get("macd_signal", 0.0) or 0.0
        is_narrow_spread = ind.get("narrow_spread", False)

        # 4. Pattern & Phase Identification (Synchronized with VSA Core Evaluator)
        is_low_supply = vol < avg_vol10
        is_above_ma50 = price >= ma50 if ma50 else False
        is_ma_aligned = (ma10 >= ma20 >= ma50) if (ma10 and ma20 and ma50) else False
        has_sector_wave = sector_wave and ("SÓNG NGÀNH CHÍNH THỨC" in sector_wave.get("status", ""))
        is_leader = sector_wave and (sector_wave.get("leader") == symbol)

        phase_name = "Pha B - Tích Lũy Chờ Đợi Dòng Tiền"
        pattern_name = "Vận Động Đi Ngang Chờ Tín Hiệu"
        matched_rules = []
        action = "QUAN SÁT CHỜ KIỆT CUNG"
        badge_type = "secondary"

        # Check Wyckoff / VSA specific setups synchronized with core evaluation
        is_breakout = ("Điểm Nổ" in rec_desc or "Breakout" in rec_desc) or (pct_change >= 4.0 and vol_ratio >= 1.4 and is_above_ma50)
        is_pivot = ("Điểm Pivot" in rec_desc) or (pct_change >= 2.0 and vol_ratio >= 1.2 and price >= ma20 and not is_breakout)
        is_cuer = ("Điểm Cược" in rec_desc or "Điểm BU" in rec_desc) or (is_low_supply and is_narrow_spread and price >= ma20 and not is_breakout and not is_pivot)
        is_sut = ("Sút" in rec_status or "Sút" in rec_desc) or (price < ma50 and pct_change < -2.0 and vol_ratio > 1.2)

        if is_breakout:
            phase_name = "Pha E - Bùng Nổ Đẩy Giá (Uptrend)"
            pattern_name = "Điểm Mua Bứt Phá (Breakout Bar / SOS)" if not is_leader else "Sói Đầu Đàn Bứt Phá (Leader SOS)"
            badge_type = "success"
            action = "MÚC - MUA MỚI / KÍCH HOẠT MARGIN"
            matched_rules.append("Quy tắc Pha E: Cổ phiếu bứt phá khỏi nền kèm khối lượng bùng nổ, xác nhận dòng tiền lớn bảo kê.")
        elif is_pivot:
            phase_name = "Pha D - Bứt Phá Từ Nền (Pocket Pivot)"
            pattern_name = "Điểm Mua Sớm (Pocket Pivot)"
            badge_type = "primary"
            action = "MÚC - MỞ VỊ THẾ 1 (12.5% TIỀN MẶT)"
            matched_rules.append("Quy tắc Pocket Pivot: Phiên bứt phá sớm từ nền sau khi đã rũ bỏ và kiệt cung, bật lên từ hỗ trợ MA10/MA20.")
        elif is_cuer:
            phase_name = "Pha D - Cạn Kiệt Cung Trước Bùng Nổ (ST / LPS)"
            pattern_name = "Điểm Mua Kiệt Cung (No Supply / Test Cung / Điểm Cược 1/8)"
            badge_type = "success"
            action = "MÚC - LẤY VỊ THẾ CƯỢC 1/8 (TIỀN MẶT)"
            matched_rules.append("Quy tắc ST/LPS: Điểm mua cược Lợi Thế Nhất bằng tiền mặt tại vùng kiệt cung (Volume < MA10).")
        elif is_sut:
            phase_name = "Pha Giảm Giá / Rũ Bỏ (Markdown)"
            pattern_name = "Thủng Hỗ Trợ / Gãy Nền Kèm Vol Lớn (Bán)"
            badge_type = "danger"
            action = "SÚT - BÁN CẮT LỖ / ĐỨNG NGOÀI"
            matched_rules.append("Quy tắc Quản Trị Rủi Ro: Giá thủng nền hoặc gãy MA50 kèm khối lượng lớn -> Thoát hàng quyết liệt bằng lệnh MB, không gồng lỗ.")
        else:
            phase_name = "Pha B - Tích Lũy Chờ Đợi Dòng Tiền"
            pattern_name = "Vận Động Đi Ngang Chờ Tín Hiệu"
            badge_type = "secondary"
            action = "QUAN SÁT CHỜ KIỆT CUNG"
            matched_rules.append("Quy tắc Kiên Nhẫn: Chưa xuất hiện điểm cược tối ưu (ST/LPS) hoặc điểm bùng nổ, kiên nhẫn đợi cung cạn kiệt.")

        # 5. Deep Knowledge-Driven Behavior Analysis (Luận giải hành vi chuẩn Sổ Tay Tri Thức & Thực Chiến)
        
        # Section 1: Bản chất Cung - Cầu & Dòng tiền lớn (Smart Money)
        if is_breakout:
            point1 = f"**1. 🧠 Bản chất Cung - Cầu & Ý chí Dòng Tiền Lớn (Smart Money):**\n" \
                     f"Phiên giao dịch bộc lộ rõ **Ý chí quyết liệt của Dòng Tiền Thông Minh (Smart Money / Big Boy)**. Khối lượng khớp lệnh ({vol:,.0f}) bùng nổ gấp **{vol_ratio:.2f} lần** so với mức trung bình 10 phiên ({avg_vol10:,.0f}), đóng vai trò là 'khoản tiền đặt cọc' và phát súng hiệu (Sign of Strength - SOS) xác nhận tổ chức chính thức bước vào Pha đẩy giá. Lệnh mua gom dứt khoát kịch trần/tăng mạnh chứng minh dòng tiền lớn sẵn sàng 'ăn trọn' toàn bộ lượng cung bán ra ở giá cao chứ không thèm gom giá rẻ."
        elif is_cuer:
            point1 = f"**1. 🧠 Bản chất Cung - Cầu & Ý chí Dòng Tiền Lớn (Smart Money):**\n" \
                     f"Cổ phiếu đang ở **Pha kiểm định Cung - Cầu then chốt (Secondary Test - ST / LPS)**. Khối lượng giao dịch sụt giảm sâu ({vol:,.0f}, chỉ bằng **{vol_ratio:.2f}x** trung bình 10 phiên), biên độ nến siết chặt. Theo sổ tay tri thức, đây là trạng thái **Kiệt Cung Lợi Thế Nhất** — toàn bộ lượng cung lơ lửng của nhỏ lẻ đã cạn kiệt, tổ chức kiểm soát hoàn toàn vùng giá vốn và tạo điểm tựa an toàn tuyệt đối theo tư duy Zero-Loss."
        elif is_pivot:
            point1 = f"**1. 🧠 Bản chất Cung - Cầu & Ý chí Dòng Tiền Lớn (Smart Money):**\n" \
                     f"Dòng tiền thông minh kích hoạt **Điểm nổ sớm (Pocket Pivot)** từ nền tích lũy. Khối lượng tăng **{vol_ratio:.2f}x** trung bình, giá bật nảy dứt khoát từ hỗ trợ MA10/MA20, báo hiệu tổ chức bắt đầu rời bệ phóng số 1 để chuẩn bị cho nhịp tăng tốc."
        elif is_sut:
            point1 = f"**1. 🧠 Bản chất Cung - Cầu & Ý chí Dòng Tiền Lớn (Smart Money):**\n" \
                     f"Cổ phiếu bị áp lực **Bán tháo áp đảo (Markdown / Gãy nền)**. Khối lượng bán ({vol:,.0f}) đạt **{vol_ratio:.2f}x** làm gãy ngưỡng hỗ trợ quan trọng. Dòng tiền lớn đã rút lui hoặc không có ý định đỡ giá, nhỏ lẻ đang rơi vào trạng thái hoảng loạn cắt lỗ."
        else:
            point1 = f"**1. 🧠 Bản chất Cung - Cầu & Ý chí Dòng Tiền Lớn (Smart Money):**\n" \
                     f"Cổ phiếu đang trong **Pha tích lũy & gom hàng (Pha B)**. Khối lượng ({vol:,.0f}) đạt **{vol_ratio:.2f}x** trung bình, chưa xuất hiện sự chênh lệch lớn giữa lực cung và lực cầu. Dòng tiền lớn tiếp tục giữ thế giằng co để rũ bỏ sự kiên nhẫn của nhà đầu tư nhỏ lẻ."

        # Section 2: Xung lực đánh & Hành vi đàn hồi (Quả bóng Tennis)
        if pct_change >= 6.0:
            point2 = f"**2. ⚡ Xung Lực Đánh & Hành Vi Đàn Hồi ('Quả Bóng Tennis'):**\n" \
                     f"Cổ phiếu bộc lộ **Xung lực đánh cực mạnh và tính cách sát phạt của đội lái**. Theo nguyên lý thực chiến trong sổ tay: *'Con nào trần đầu tiên thì múc'* — lệnh quét trần kịch biên độ (+{pct_change:.2f}%) tạo độ dốc Parabol bám sát MA10, ép toàn bộ thị trường phải mua đuổi giá cao. Cổ phiếu thể hiện phẩm chất của một **'Quả bóng Tennis'** có độ nảy mạnh mẽ nhất khi thị trường đảo chiều."
        elif pct_change >= 3.0:
            point2 = f"**2. ⚡ Xung Lực Đánh & Hành Vi Đàn Hồi ('Quả Bóng Tennis'):**\n" \
                     f"Xung lực giá tăng dứt khoát (+{pct_change:.2f}%), giữ vững cấu trúc nến tăng thân đặc. Độ đàn hồi của cổ phiếu tốt hơn mặt bằng chung, bám sát các đường MA ngắn hạn hướng lên."
        elif is_cuer:
            point2 = f"**2. ⚡ Xung Lực Đánh & Hành Vi Đàn Hồi ('Quả Bóng Tennis'):**\n" \
                     f"Biên độ dao động thu hẹp tối đa (Narrow Spread), nến đi ngang kiệt Vol. Trạng thái này như chiếc lò xo nén chặt, khi thị trường chung rung lắc cổ phiếu không bị rơi mà giữ vững nền giá, sẵn sàng bật nảy mạnh như quả bóng tennis ngay khi có dòng tiền kích hoạt."
        elif is_sut:
            point2 = f"**2. ⚡ Xung Lực Đánh & Hành Vi Đàn Hồi ('Viên Gạch Rơi'):**\n" \
                     f"Cổ phiếu hành xử như một **'Viên gạch'**, mất hoàn toàn tính đàn hồi khi thị trường giảm điểm. Lực cầu bắt đáy yếu ớt, giá trượt dốc không phanh."
        else:
            point2 = f"**2. ⚡ Xung Lực Đánh & Hành Vi Đàn Hồi ('Quả Bóng Tennis'):**\n" \
                     f"Độ đàn hồi ở mức trung bình. Cần quan sát thêm phản ứng của cổ phiếu tại các nhịp rung lắc của VN-Index để nhận diện xem đây là 'Quả bóng Tennis' hay 'Viên gạch'."

        # Section 3: Bối cảnh Sóng Ngành & Gió Đông Thị Trường Chung
        if has_sector_wave and is_leader:
            point3 = f"**3. 🌊 Bối Cảnh Sóng Ngành & 'Gió Đông' Thị Trường Chung:**\n" \
                     f"Hội tụ hoàn hảo điều kiện **'Gió Đông' & Sóng Ngành Dẫn Dắt**: Nhóm **{sector_name}** đang có sóng ngành chính thức (Con Tàu Mẹ), và cổ phiếu đang giữ vai trò **'Sói Đầu Đàn' (Leader)** vượt đỉnh đầu tiên. Theo kinh nghiệm sổ tay, khi thị trường chung thuận lợi và cả dòng cùng đồng loạt 'nhổ giò', xác suất chiến thắng của điểm mua Breakout được nâng lên đến 95%."
        elif has_sector_wave:
            point3 = f"**3. 🌊 Bối Cảnh Sóng Ngành & 'Gió Đông' Thị Trường Chung:**\n" \
                     f"Hưởng lợi trực tiếp từ **Sóng dòng {sector_name}**. Sự đồng thuận của các mã cùng ngành tạo tấm đệm an toàn vững chắc, giảm thiểu tối đa rủi ro điều chỉnh đơn lẻ."
        else:
            point3 = f"**3. 🌊 Bối Cảnh Sóng Ngành & 'Gió Đông' Thị Trường Chung:**\n" \
                     f"Cổ phiếu đang vận động riêng lẻ hoặc thuộc nhóm ngành chưa có sự xác nhận của Sóng Dòng. Cần nghiêm ngặt tuân thủ nguyên tắc: *'Đừng mò kim cương trong bể cứt'*, tuyệt đối không mua cổ phiếu dính phốt hoặc ngành đang bị bán tháo."

        # Section 4: Đối Chiếu Mẫu Hình Tham Chiếu (Case Studies: Thành Công vs Thất Bại)
        case_studies = self.km.get_case_studies_summary()
        if is_breakout:
            point4 = f"**4. 🎯 Đối Chiếu Mẫu Hình Thực Chiến (Case Studies Tham Chiếu):**\n" \
                     f"• **Mẫu hình Thành Công tương đồng:** Trùng khớp với **Mẫu hình Siêu Cổ Phiếu Vượt Đỉnh (Leader SOS / Nền Số 2)** trong sổ tay (như Case Study FTS, VIX, BSI sóng Chứng khoán 2023 hay MSB, TCB tạo nền dốc lên): Nổ Vol chọc trời + Tăng trần sớm nhất dòng + Sóng ngành bảo trợ -> Kích hoạt chu kỳ chạy nước rút 30-50%.\n" \
                     f"• **Cảnh báo Mẫu hình Thất Bại:** Cần cảnh giác với bẫy *'Upthrust / Breakout Xịt'* nếu phiên kế tiếp quay đầu giảm phủ nhận nến nổ hoặc VN-Index đánh gãy MA50."
        elif is_cuer:
            point4 = f"**4. 🎯 Đối Chiếu Mẫu Hình Thực Chiến (Case Studies Tham Chiếu):**\n" \
                     f"• **Mẫu hình Thành Công tương đồng:** Trùng khớp với **Mẫu hình Cược Điểm Tựa Zero-Loss (ST / LPS kiệt cung)** trong sổ tay: Mua tại nền cạn kiệt khối lượng, rủi ro lỗ vốn cực thấp (nếu sai cắt lỗ hòa vốn hoặc 1-2%).\n" \
                     f"• **Cảnh báo Mẫu hình Thất Bại:** Nếu nền giá bị đè gãy với khối lượng lớn bất thường (Gãy nền rũ thất bại), phải lập tức đóng vị thế theo kỷ luật."
        elif is_sut:
            point4 = f"**4. 🎯 Đối Chiếu Mẫu Hình Thực Chiến (Case Studies Tham Chiếu):**\n" \
                     f"• **Mẫu hình Thất Bại kinh điển:** Trùng khớp với **Mẫu hình Bẫy Bắt Đáy / Phân Phối Cắt Lỗ** (như các case PC1 rơi sàn, TV2, HDG khi dính phốt pháp lý/bán tháo). Tuyệt đối không bắt đáy vì tưởng rẻ."
        else:
            point4 = f"**4. 🎯 Đối Chiếu Mẫu Hình Thực Chiến (Case Studies Tham Chiếu):**\n" \
                     f"Cổ phiếu chưa xuất hiện mẫu hình bùng nổ rõ rệt. Tiếp tục đối chiếu với 5 Tiêu Chí Vàng trong sổ tay để chờ đợi tín hiệu kích hoạt chuẩn xác."

        if case_studies:
            point4 += f"\n*(Hệ thống đã tự động liên kết với {len(self.km.list_knowledge())} tài liệu thực chiến trong thư mục `knowledge_base/`)*"

        # Section 5: Đánh Giá Xác Suất Machine Learning 20 Năm HOSE & So Khớp Mẫu Hình
        point5 = ""
        try:
            from data_pipeline.ml_inference import VSAMLInferenceEngine
            from data_pipeline.pattern_matcher import VSAPatternMatcher
            ml_engine = VSAMLInferenceEngine()
            pred = ml_engine.predict_symbol_date(symbol, stock_eval.get("date"))
            if pred.get("status") != "error":
                t1 = pred["tier1_cuoc"]
                t2 = pred["tier2_pocket"]
                t3 = pred["tier3_pivot"]
                rec1 = "✅ Đạt chuẩn cược" if t1["is_recommended"] else "Chưa đạt"
                rec2 = "✅ Đạt chuẩn Pocket" if t2["is_recommended"] else "Chưa đạt"
                rec3 = "✅ Nổ an toàn" if t3["is_recommended"] else "Cảnh giác bẫy nổ xịt"
                
                point5 = f"**5. 🤖 Đánh Giá Xác Suất Học Máy (Machine Learning 20 Năm HOSE):**\n" \
                         f"• **Tầng 1 (Điểm Cược Zero-Loss):** {t1['probability_pct']:.1f}% ({t1['evaluation']} - {rec1})\n" \
                         f"• **Tầng 2 (Điểm Đẩy Nền Pocket):** {t2['probability_pct']:.1f}% ({t2['evaluation']} - {rec2})\n" \
                         f"• **Tầng 3 (Điểm Pivot Zero Đỉnh):** {t3['probability_pct']:.1f}% ({t3['evaluation']} - {rec3})"
                         
            pat_matcher = VSAPatternMatcher()
            pat_res = pat_matcher.match_pattern(symbol, stock_eval.get("date"))
            if pat_res.get("status") == "success":
                sim = pat_res.get("similarity_score_pct", 0)
                pat_name = pat_res.get("best_match_pattern", "")
                ref = pat_res.get("reference_stock", "")
                res_hist = pat_res.get("historical_result", "")
                img_f = pat_res.get("image_file", "")
                img_ind = pat_res.get("image_indicators", "")
                point5 += f"\n• **🔍 So khớp Sổ tay Mẫu hình:** {pat_name} (Độ tương đồng: {sim:.1f}%, ca mẫu đối chiếu: {ref} - {res_hist})"
                if img_f:
                    point5 += f"\n• **🖼️ Biểu đồ thị giác liên kết:** `{img_f}`"
                if img_ind:
                    point5 += f"\n• **📊 Tín hiệu chỉ báo đồ thị:** {img_ind}"
        except Exception:
            pass

        if point5:
            behavior_analysis = f"{point1}\n\n{point2}\n\n{point3}\n\n{point4}\n\n{point5}"
        else:
            behavior_analysis = f"{point1}\n\n{point2}\n\n{point3}\n\n{point4}"

        # 6. Tactical Action Plan (Công thức đi vốn 4x2 & Margin)
        stop_loss_price = round(price * 0.94, 2)
        target_tp1 = round(price * 1.15, 2)
        target_tp2 = round(price * 1.30, 2)

        if is_breakout:
            entry_1_desc = f"Vùng giá {price:,.2f} (MUA MỚI ngay tại phiên nổ - 12.5% Tiền mặt)"
            entry_2_desc = f"Khi giá tiếp tục duy trì xung lực hoặc tại nhịp BU test lại đỉnh -> Nhồi thêm 12.5% bằng MARGIN"
        elif is_pivot:
            entry_1_desc = f"Vùng giá {round(price * 0.98, 2):,.2f} - {price:,.2f} (Mở vị thế sớm 12.5% bằng TIỀN MẶT)"
            entry_2_desc = f"Chờ phiên bùng nổ vượt nền (Breakout SOS) -> Kích hoạt nhồi thêm 12.5% MARGIN"
        elif is_cuer:
            entry_1_desc = f"Vùng giá nền {round(price * 0.98, 2):,.2f} - {price:,.2f} (Lấy vị thế cược 12.5% bằng TIỀN MẶT)"
            entry_2_desc = f"Chờ điểm nổ Pivot/Breakout -> Nhồi thêm 12.5% bằng MARGIN"
        elif is_sut:
            entry_1_desc = "KHÔNG MUA - Đang trong pha giảm giá hoặc gãy nền hỗ trợ"
            entry_2_desc = "TUYỆT ĐỐI KHÔNG DÙNG MARGIN ĐỂ BẮT ĐÁY"
        else:
            entry_1_desc = f"Quan sát vùng giá {round(price * 0.98, 2):,.2f} - {price:,.2f} (Đợi cạn cung ST/LPS mới giải ngân)"
            entry_2_desc = "Chưa kích hoạt điều kiện sử dụng Margin"

        stop_loss_desc = f"Cắt lỗ dứt khoát tại {stop_loss_price:,.2f} (Âm 6%) hoặc khi thủng MA50 ({ma50:,.2f}) với Vol lớn."
        take_profit_desc = f"Mục tiêu 1 (+15%): {target_tp1:,.2f} (Chốt lời phần Margin). Mục tiêu 2 (+30%): {target_tp2:,.2f} (Giữ theo sóng lớn)."
        capital_alloc_desc = "Phân bổ danh mục tối đa 4 cổ phiếu (25% vốn mỗi mã). Mỗi mã chia làm 2 đợt giải ngân (12.5% Tiền mặt + 12.5% Margin)."

        risk_warning = "Không mua đuổi nếu giá đã chạy quá 4% từ nền hỗ trợ. Tuyệt đối không dùng Margin để trung bình giá xuống khi cổ phiếu giảm."
        if not is_above_ma50:
            risk_warning = "⚠️ CẢNH BÁO: Cổ phiếu nằm dưới MA50, rủi ro cao. Tuyệt đối KHÔNG sử dụng Margin ở vùng này."

        # 7. Compile Final Diagnostic Package
        diagnosis = {
            "symbol": symbol,
            "date": stock_eval.get("date", datetime.now().strftime("%Y-%m-%d")),
            "latest_price": price,
            "price_change_pct": pct_change,
            "vsa_score": vsa_score,
            "badge_type": badge_type,
            "phase_name": phase_name,
            "pattern_name": pattern_name,
            "action": action,
            "behavior_analysis": behavior_analysis,
            "matched_rules": matched_rules,
            "actionable_plan": {
                "entry_point_1": entry_1_desc,
                "entry_point_2": entry_2_desc,
                "stop_loss": stop_loss_desc,
                "take_profit": take_profit_desc,
                "capital_allocation": capital_alloc_desc
            },
            "risk_warning": risk_warning,
            "sector_context": {
                "sector_name": sector_name,
                "has_wave": has_sector_wave,
                "wave_status": sector_wave.get("status", "Chưa xác định") if sector_wave else "Không thuộc 3 nhóm ngành chính",
                "is_leader": is_leader
            }
        }
        return diagnosis


def generate_detailed_reasoning(eval_res):
    """
    Generates tailored conversational insights from Trio: Sâu FOMO, Huệ Quyên, and Bé Đậu.
    """
    engine = ReasoningEngine()
    diag = engine.diagnose_stock(eval_res)
    desc = eval_res.get("recommendation_desc", "")
    status = eval_res.get("recommendation_status", "Theo dõi")
    score = eval_res.get("score", 50)
    sym = eval_res.get("symbol", "")
    
    if "Điểm Cược" in desc or "kiệt cung" in desc.lower():
        sau_text = f"Ôi {sym} nến xanh rút chân đẹp quá! Giá đang rẻ thế này em tính tất tay full Margin phiên mai luôn cho máu, chậm chân là ngồi nhìn người khác nhân đôi tài khoản mất!"
        hq_text = f"Bình tĩnh nào Sâu FOMO ơi! Đừng để cảm xúc hưng phấn che mờ lý trí. Hãy nhìn khối lượng: Vol hôm nay chỉ ở mức kiệt quệ, đây là vùng Smart Money gom hàng trong tĩnh lặng chứ chưa hề có phiên nổ đẩy giá chính thức (Pha E). Tuyệt đối không được fomo đu giá cao!"
        dau_text = f"Em cấm Sâu FOMO dùng Margin vùng này nhé! Tiền của chúng ta phải giữ như giữ vàng. Kế hoạch chuẩn: Mở vị thế Điểm Cược 1/8 (12.5% tiền mặt). Điểm dừng lỗ đặt ngay dưới đáy nến kiệt cung (-2.0%). Nếu gãy nền là cắt dứt khoát, đúng bài Zero-Loss mới sống lâu được trên sàn!"
    elif "Pocket" in desc:
        sau_text = f"Đấy thấy chưa, {sym} vào sóng lớn rồi! Tiền to cuồn cuộn thế này phải đua lệnh nhồi thêm Margin kịch khung ngay, chậm 1 giây là lỡ tàu thế kỷ!"
        hq_text = f"Xuất hiện phiên đẩy nền Pocket Pivot tại {sym}! Lực cầu hấp thụ lượng cung lỏng lẻo rất mượt mà. Tuy nhiên đây mới chỉ là nhịp đẩy nền số 2, chưa phải lúc để all-in."
        dau_text = f"Đã có vị thế Điểm Cược chân nền thì phiên hôm nay em cho phép Sâu FOMO gia tăng đợt 2 (lên 25% tiền mặt). Tuyệt đối vẫn CHƯA được dùng Margin vội, phải đợi đệm lãi dày mới tính tiếp nhé!"
    elif "Breakout" in desc or "Điểm Nổ" in desc:
        sau_text = f"TÍM RỒI! Siêu cổ phiếu {sym} bùng nổ vượt đỉnh rồi! Đua lệnh bất chấp giá trần đi cả nhà ơi, không mua hôm nay là mai không còn hàng mà mua đâu!"
        hq_text = f"Cổ phiếu {sym} bùng nổ vượt đỉnh (Pha E), dòng tiền lớn xác nhận nhập cuộc. Nhưng lưu ý: Nếu mua mới tại phiên nổ phải cực kỳ cẩn trọng, kiểm tra xem có sóng ngành bảo trợ hay không để tránh bẫy Upthrust!"
        dau_text = f"Sâu FOMO cứ thấy trần là mắt sáng rực lên! Nhớ quy tắc Zero Đỉnh: Sau phiên nổ 2-5 ngày phải có lãi và không được gãy 1/2 thân nến nổ. Ai chưa có vị thế từ nền thì tuyệt đối không được đu lệnh giá tím!"
    elif "Sút" in status:
        sau_text = f"Trời đất ơi sập rồi, {sym} gãy nền nát bét rồi! Bán tháo sạch sành sanh ngay kẻo nó rơi về đồ đá trắng bên mua bây giờ, sợ quá chạy thôi!"
        hq_text = f"CẢNH BÁO NGUY HIỂM: Cổ phiếu {sym} đã bị đánh gãy nền hỗ trợ then chốt với điểm VSA giảm sâu ({score:.1f}/100). Đang trong pha phân phối hoặc đè giá của Big Boys. Sâu FOMO hoảng loạn nhưng lần này chạy là đúng hướng!"
        dau_text = f"Lần này em đồng ý với Sâu FOMO! Tuyệt đối KHÔNG BẮT ĐÁY, KHÔNG GỒNG LỖ, KHÔNG DÙNG MARGIN ĐỂ TRUNG BÌNH GIÁ XUỐNG. Bán dứt khoát bảo toàn tiền mặt, còn tiền là còn cơ hội làm lại!"
    else:
        sau_text = f"Cổ phiếu {sym} cứ lình xình chán ngắt thế này, hay là em bán quách đi nhảy sang mấy con Penny đang trần tím ngoài kia cho nhanh giàu nhỉ chị Quyên ơi?"
        hq_text = f"Cổ phiếu {sym} đang trong quá trình tích lũy và kiểm định cung cầu (Điểm VSA: {score:.1f}/100). Đang siết biên độ nền giá thì phải kiên nhẫn chờ đợi, nhảy nhót lung tung chỉ làm mồi cho lái thôi!"
        dau_text = f"Kiên nhẫn là chìa khóa Sâu FOMO ơi! Chưa xuất hiện Điểm Cược kiệt cung chuẩn bài thì em cứ ôm tiền mặt đứng ngoài quan sát, thị trường không bao giờ thiếu cơ hội cho người có kỷ luật!"

    return {
        "sau_fomo": sau_text,
        "hue_quyen": hq_text,
        "be_dau": dau_text,
        "diagnosis": diag
    }
