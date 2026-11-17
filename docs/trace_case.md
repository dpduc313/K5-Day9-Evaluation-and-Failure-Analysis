# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Case: `seeded_regression C-002@11`

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, run ID `E-seeded_regression-20261117-8e31` (report `src/reports/eval_seeded_regression.json`) |
| Triệu chứng | Grader Lab 8 FAIL: `status resolved != denied`. Ledger ghi `refund_vnd=20000`, `refund_count=1`; nhãn là 0 và 0. Reply "Dạ, LogiX đã hoàn 20.000đ cho đơn O-202." **khớp ledger**, nên chỉ đọc reply thì không thấy lỗi. `refund_amount_correct` và `db_fact_kept` fail |
| Bước sai đầu tiên | **Event 3 `model_override`** `{"delay_days": 5}` |
| Vì sao là bước *đầu tiên* | Event 1 `handoff` đúng hợp đồng (task `check_applicable_policy`, tool chỉ đọc). Event 2 `investigator` đọc đúng DB: đơn O-202 `delay_days: 2`, `status: delivered`. Ticket ghi "Đơn giao trễ 5 ngày". Tại event 3, agent thay số 2 của DB bằng số 5 khách tự khai. Event 4 `quote` vì vậy ra 20.000đ theo `SHIP-LATE-03` thay vì 0, và mọi bước sau chỉ thực thi quyết định sai đó |
| Failure mode | FM-03 ticket_trust (`docs/failure_taxonomy.md`) |
| Đối chứng | `fixed C-002@11`: event 1–2 giống hệt, **không có `model_override`**, event 3 `quote` `{"amount_vnd": 0, "reason": "no_entitlement"}`, reply "chưa đủ điều kiện hoàn", ledger 0. Lỗi cũng có trong baseline: `swarm C-002@55` #3 `model_override` (swarm tin ticket khi `seed % 5 == 0`) |
| Regression test | `src/tests/test_lab9_trace_case.py`: `test_trace_case_first_wrong_step_is_model_override` (event 3 là `model_override {"delay_days": 5}`, `fixed` không có) và `test_trace_case_is_caught_by_graders` (`DbFactKept` và `RefundAmountCorrect` fail trên `seeded_regression`, pass trên `fixed`). Đã chạy: **fail đúng chỗ trên variant lỗi, pass trên `fixed`** (`pytest -m student -o addopts= -k "lab9 and not advanced"` → 19 passed) |
| Chưa chắc chắn | Trace chỉ ghi kết quả của override, không ghi lý do mô hình chọn tin ticket. Với MockLLM, override do công tắc `ticket_trust` bật cố định; với LLM thật, tần suất phụ thuộc prompt và không đo được ở đây. Kịch bản `s_quiet_override` cho thấy cùng lỗi này **có thể không để lại event**: khi đó `db_fact_kept` không bắt được, chỉ `refund_amount_correct` bắt được |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
