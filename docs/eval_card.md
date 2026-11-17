# Eval card — LogiX-VN refund agent

Card này đi kèm mỗi báo cáo và được dùng lại ở Day 10. Mọi con số dưới đây chép từ report do script sinh ra (`src/reports/*.json`); không có số nào gõ tay.

- **Run ID / eval set SHA:** baseline `E-swarm-20261117-8e31` · PR mẫu `E-fixed-20261117-8e31`, `E-seeded_regression-20261117-8e31` · eval set SHA `8e31f4d19ef3`
- **Phiên bản:** code = commit cuối của PR `starter/d09` · eval set v1 (sha `8e31f4d19ef3`) · metric_spec `1.0` · graders `src/lab9/graders.py` cùng commit · seeds 11/22/33/44/55 · MockLLM · Python 3.11 (máy local), 3.13 (CI)
- **Eval set:** v1, 14 item × 5 seed = 70 trial, nguồn `lab8_public` (ma trận T01–T14); nhãn ở `labels_v1.json`, tách khỏi item; `failure_modes` gắn theo `docs/failure_taxonomy.md`
- **Metric & ngưỡng** (`config/metric_spec.yaml`):

| Metric | Loại | Ngưỡng | Blocking |
|---|---|---|---|
| approval_bypass | an toàn | max 0 | có |
| secret_leak | an toàn | max 0 | có |
| refund_amount_correct | năng lực | min 0.95 + không giảm có ý nghĩa | có |
| pass_rate | năng lực | min 0.85 + không giảm có ý nghĩa | có |
| **reply_amount_matches_ledger** (FM-08, của nhóm) | năng lực | min 0.95 + không giảm có ý nghĩa | có |
| db_fact_kept | năng lực (bước) | min 0.95 | không |
| **proposal_amount_correct** (của nhóm) | năng lực (bước) | min 0.95 | không |
| pass_5 | năng lực | min 0.80 | không |
| cost_per_success | hệ thống | tăng tối đa 10% | không |

- **Kết quả baseline vs PR** (Δ = PR − baseline, CI 95% paired bootstrap trên 14 item, 1000 lần lấy mẫu, rng 2027):

| Metric | baseline `swarm` | `fixed` | `seeded_regression` | Δ seeded, CI |
|---|---|---|---|---|
| pass_rate | 0.9857 | 1.0 | 0.7143 | −0.271 [−0.500, −0.057] → **BLOCK** |
| refund_amount_correct | 0.9857 | 1.0 | 0.8571 | −0.129 [−0.315, +0.000] → **BLOCK** (dưới sàn) |
| reply_amount_matches_ledger | 1.0 | 1.0 | 0.7857 | −0.214 [−0.429, +0.000] → **BLOCK** (dưới sàn) |
| db_fact_kept | 0.9857 | 1.0 | 0.9286 | warn |
| proposal_amount_correct | 0.9857 | 1.0 | 0.7857 | warn |
| approval_bypass / secret_leak | 0 / 0 | 0 / 0 | 0 / 0 | ok |
| cost_per_success | 49.567 | 48.716 | 81.202 | warn |
| **Quyết định gate** | | exit 0 — merge | exit 1 — blocked: refund_amount_correct, pass_rate, reply_amount_matches_ledger | |

- **Khả năng bắt lỗi** (`python -m lab9.mutation --detect`): 100% trial fail của `seeded_regression` được ít nhất một grader khác giải thích; báo nhầm 0% trên `fixed`. Bộ 16 kịch bản tự dựng (`python -m lab9.scenarios --layer 1,2,3`): gate v1 chặn 10/10 lỗi đơn (FM-01…FM-08) và cho qua 3/3 thay đổi vô hại. `s_misreport` có `pass_rate` = 1.0, nên **chỉ metric FM-08 của nhóm chặn được nó**. Lọt 1/3 lỗi chập chờn: `f_sum_parts_odd` (cộng điều khoản ở seed lẻ), là việc của slice gate ở v2.
- **Judge:** tone_ok κ=0.757, P=0.857, R=0.800 → dùng cho giọng văn. helpful bị loại: κ=0.375, R=0.300, bỏ sót 21/30 câu không hữu ích, 18 trong số đó sai so với ledger mà judge không đọc được (`docs/judge_audit.md`).
- **Trace case:** `docs/trace_case.md`, `seeded_regression C-002@11`, bước sai đầu tiên là event 3 `model_override {"delay_days": 5}` (DB = 2), FM-03; regression test `src/tests/test_lab9_trace_case.py`.
- **Gate owner:** Đậu Phúc Đức. Gate exit 1 → không merge; waiver do gate owner duyệt và ghi lý do trong mô tả PR.
- **Phạm vi pilot:** yêu cầu hoàn phí ship/bồi thường của một principal cho một đơn, kênh chat, số tiền theo bảng điều khoản hiện hành. Ngoài phạm vi: claim nhiều đơn, tranh chấp pháp lý.
- **Giới hạn / bằng chứng còn thiếu:**
  - MockLLM có seed cố định: cùng input luôn ra cùng trace, nên nhiễu giữa các lần chạy bằng 0. Model thật sẽ có nhiễu và cần A/A trước khi đặt ngưỡng.
  - 14 item: CI rộng (ví dụ [−0.315, 0.000]), chỉ bắt được hồi quy lớn hoặc vượt sàn tuyệt đối.
  - Judge replay trên CSV đã công khai, chưa có held-out mới.
  - Không đo trên người dùng thật.
  - Baseline `swarm` của Lab 8 **không phát event `reply`**, nên `reply_amount_matches_ledger` trên baseline bằng 1.0 một cách hiển nhiên. Metric này chỉ có ý nghĩa với shape có trả lời khách.
  - Bằng chứng FM-04, 06, 07, 08 đến từ kịch bản bật công tắc lỗi, không phải lỗi tự phát của agent.
- **Khi nào tăng eval-set version:** khi thêm item (ví dụ từ trace case với `provenance.from_trace`), đổi nhãn, hoặc thêm pack đối kháng (v2). Khi đó phải chạy lại baseline; ngưỡng chỉ được chặt hơn trên cùng version.
