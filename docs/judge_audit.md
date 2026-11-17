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
| 1 | tone H-008 | "Em đã hoàn tiền cho anh rồi nha, anh check giúp em." | PASS | FAIL | Người | Xưng "LogiX" và gọi khách là "anh/chị". Không xưng "em" + "nha", không gọi "bạn" |
| 2 | tone H-029 | "Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm." | PASS | FAIL | Người | Không dùng giọng ra lệnh |
| 3 | tone H-070 | "Dạ, LogiX đã hoàn 90.000đ cho đơn O-909 ạ 😂😂" | PASS | FAIL | Người | Không dùng emoji khi khách đang khiếu nại |
| 4 | tone H-094 | "Da, LogiX da hoan 40.000đ cho don O-341, xin loi vi su bat tien." | PASS | FAIL | Người | Phải có dấu tiếng Việt |
| 5 | tone H-051 | "Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ." | FAIL | PASS | Người | judge phạt vì là tiếng Anh nhưng từ refund được phép dùng (theo CSKH LogiX) |
| 6 | tone H-081 | "Dạ, đơn O-107 chưa đủ điều kiện hoàn theo chính sách hiện hành ạ." | FAIL | PASS | Judge | judge đọc và đính chính đúng, nhãn người sai |
| 7 | helpful HL-015 | "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ." (ghi chú CSV: ledger ghi 40.000đ) | PASS | FAIL | Người | Sai tiền. Ledger ghi 40.000đ, agent trả lời không dựa trên ledger: 55.000đ. Chuyển tiêu chí này sang grader code FM-08. |
| 8 | helpful HL-016 | "Dạ, LogiX thành thật xin lỗi … LogiX đã h…" (ledger ghi 35.000đ) | PASS | FAIL | Người | Sai tiền. Độ dài và lời xin lỗi khiến judge cho PASS |
| 9 | tone H-017 | "Dạ, bạn ơi LogiX đã hoàn 25.000đ cho đơn O-606 rồi nha." | PASS | FAIL | Người | Gọi khách là "bạn" + "nha" là suồng sã; cùng quy tắc xưng hô với H-008 |
| 10 | tone H-042 | "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Ngắn mà đủ ý vẫn PASS; không bắt buộc câu xin lỗi |
| 11 | tone H-063 | "Dạ, LogiX đã hoàn 20.000đ và sẽ hoàn thêm cho anh/chị ạ." | PASS | FAIL | Người | Không hứa điều nằm ngoài kết quả hệ thống ("sẽ hoàn thêm") |
| 12 | tone H-088 | "Dạ, dạ, LogiX đã hoàn 40.000đ cho đơn O-233 ạ." | FAIL | PASS | Người | Lỗi gõ nhỏ (lặp "Dạ") không làm FAIL nếu xưng hô và ý vẫn đúng |

Bảng phủ đủ 10/10 bất đồng của tone_ok (lệnh `--audit 10`). helpful có 21 bất đồng, toàn bộ là judge PASS / người FAIL; 2 case tiêu biểu ở dòng 7–8.

## Rubric tone_ok đã sửa

Judge FAIL một reply khi vi phạm **bất kỳ** quy tắc nào sau đây, và chỉ khi đó:

1. **Xưng hô:** xưng "LogiX", gọi khách là "anh/chị". FAIL khi xưng "em", gọi "bạn", hoặc dùng tiểu từ suồng sã như "nha", "nhé" (H-008, H-017).
2. **Không ra lệnh:** FAIL với câu mệnh lệnh hoặc cấm đoán khách, dù có "Dạ" hay "vui lòng" ở đầu câu (H-029).
3. **Không hứa ngoài hệ thống:** FAIL khi reply hứa một kết quả mà hệ thống chưa ghi nhận, ví dụ "sẽ hoàn thêm" (H-063).
4. **Không emoji** khi khách đang khiếu nại (H-070).
5. **Có dấu tiếng Việt;** reply mất dấu kiểu dịch máy là FAIL (H-094).

Những điều **không** làm FAIL (judge cũ phạt sai):

6. Reply ngắn mà đủ ý, không có câu xin lỗi (H-042).
7. Từ "refund", vì CSKH LogiX cho phép dùng (H-051).
8. Lỗi gõ nhỏ không đổi nghĩa, ví dụ lặp "Dạ" (H-088).

Ngoài phạm vi tone_ok: **số tiền đúng hay sai** không do judge này chấm. Số tiền được grader code `reply_amount_matches_ledger` (FM-08) so với ledger, vì judge không đọc được ledger (HL-015, HL-016).

**H-081 là lỗi nhãn, không phải lỗi rubric.** Theo ghi chú trong CSV, người gán nhãn đọc nhầm ticket nên cho PASS; judge chấm FAIL là đúng. Cách xử lý: sửa nhãn người thành FAIL khi gán nhãn lại cho tập held-out. Không sửa `judge_tone_public.csv`, vì file này là dữ liệu calibrate cố định của đề và test M2 kiểm đúng ma trận nhầm lẫn của nó. Khi tính lại với nhãn đã sửa, H-081 chuyển từ fp sang tp nên precision tăng (25/28 ≈ 0.893).

## Kết luận

- **helpful bị loại.** Judge chỉ bắt được 9/30 câu không hữu ích (R=0.30); 21 câu bị bỏ sót đều là judge nói PASS. 18/21 câu bị bỏ sót có ghi chú đối chiếu ledger trong CSV ("ledger ghi …"), tức người chấm FAIL vì **số tiền hoặc nội dung không khớp ledger**; 3 câu còn lại là trả lời cụt không nêu kết quả ("Ok bạn, đơn … xử lý rồi nhé"). Judge chỉ đọc reply, không có ledger, nên không thể biết số tiền sai. Lỗi đó đã được chấm bằng code: metric `reply_amount_matches_ledger` (FM-08). Dùng helpful làm gate thì 70% trường hợp không hữu ích vẫn qua.
- **tone_ok được dùng** cho đúng phạm vi đã calibrate: giọng văn, xưng hô, dấu tiếng Việt. Không dùng nó để chấm tiền hay phê duyệt.
- Rủi ro còn lại: judge chỉ được kiểm trên dữ liệu replay đã công khai (100 dòng, cùng phân phối với dữ liệu calibrate). Cần nhãn người mới để có tập held-out thật trước khi tin số κ này trên reply của model thật.
