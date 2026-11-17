# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5`

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | Đạt | **dùng** (chỉ cho giọng văn, không cho tiền) |
| helpful | 100 | 0.375 | 1.000 | 0.300 | **Không** (κ và R dưới sàn) | **loại** |

Ma trận nhầm lẫn (FAIL là lớp dương):
- tone_ok: tp 24, fp 4, fn 6, tn 66. Tỉ lệ FAIL quan sát 0.28 → hiệu chỉnh Rogan-Gladen 0.30.
- helpful: tp 9, fp 0, fn 21, tn 70. Tỉ lệ FAIL quan sát 0.09 → hiệu chỉnh 0.30.

## ≥5 case audit thủ công

Cột "Judge nói" và "Người nói" lấy từ CSV. **Cột "Ai đúng?" và "Sửa rubric" do tác giả tự đọc reply rồi điền.**

| # | Case | Reply (trích) | Judge nói | Người nói | Ai đúng? | Sửa rubric |
|---|---|---|---|---|---|---|
| 1 | tone H-008 | "Em đã hoàn tiền cho anh rồi nha, anh check giúp em." | PASS | FAIL | | |
| 2 | tone H-029 | "Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm." | PASS | FAIL | | |
| 3 | tone H-070 | "Dạ, LogiX đã hoàn 90.000đ cho đơn O-909 ạ 😂😂" | PASS | FAIL | | |
| 4 | tone H-094 | "Da, LogiX da hoan 40.000đ cho don O-341, xin loi vi su bat tien." | PASS | FAIL | | |
| 5 | tone H-051 | "Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ." | FAIL | PASS | | |
| 6 | tone H-081 | "Dạ, đơn O-107 chưa đủ điều kiện hoàn theo chính sách hiện hành ạ." | FAIL | PASS | | |
| 7 | helpful HL-015 | "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ." (ghi chú CSV: ledger ghi 40.000đ) | PASS | FAIL | | |
| 8 | helpful HL-016 | "Dạ, LogiX thành thật xin lỗi … LogiX đã h…" (ledger ghi 35.000đ) | PASS | FAIL | | |

Các bất đồng còn lại: tone H-017, H-042, H-063, H-088 (lệnh `--audit 10`); helpful 21 case, toàn bộ là judge PASS / người FAIL.

## Kết luận

- **helpful bị loại.** Judge chỉ bắt được 9/30 câu không hữu ích (R=0.30); 21 câu bị bỏ sót đều là judge nói PASS. 18/21 câu bị bỏ sót có ghi chú đối chiếu ledger trong CSV ("ledger ghi …"), tức người chấm FAIL vì **số tiền hoặc nội dung không khớp ledger**; 3 câu còn lại là trả lời cụt không nêu kết quả ("Ok bạn, đơn … xử lý rồi nhé"). Judge chỉ đọc reply, không có ledger, nên không thể biết số tiền sai. Lỗi đó đã được chấm bằng code: metric `reply_amount_matches_ledger` (FM-08). Dùng helpful làm gate thì 70% trường hợp không hữu ích vẫn qua.
- **tone_ok được dùng** cho đúng phạm vi đã calibrate: giọng văn, xưng hô, dấu tiếng Việt. Không dùng nó để chấm tiền hay phê duyệt.
- Rủi ro còn lại: judge chỉ được kiểm trên dữ liệu replay đã công khai (100 dòng, cùng phân phối với dữ liệu calibrate). Cần nhãn người mới để có tập held-out thật trước khi tin số κ này trên reply của model thật.
