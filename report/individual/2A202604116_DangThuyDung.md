# Báo cáo cá nhân — Day 6

## Dữ liệu và pipeline
- **Chủ đề, nguồn/quyền, số trang và quy tắc tính trang:** Sách *Psychology 2e* (OpenStax), Chương 1 "Introduction to Psychology" và Chương 2 "Psychological Research". Nguồn: https://openstax.org/details/books/psychology-2e, truy cập ngày 14/11/2026. Giấy phép: CC BY-NC-SA 4.0 (©2026 Rice University) ** "©2026 Rice University. Creative Commons Attribution Non-Commercial ShareAlike 4.0 International License (CC BY-NC-SA 4.0). Cho phép chia sẻ, remix, phát triển nội dung cho mục đích phi thương mại; bản chuyển thể phải dùng cùng loại giấy phép; phải giữ ghi nguồn 'Access for free at openstax.org.**. Phiên bản: . PDF có 755 trang vật lý. Offset trang PDF = trang in + 12, đã kiểm chứng bằng chân trang ở các trang biên. Chương 1 lấy PDF 19–41 (23 trang), Chương 2 lấy PDF 47–74 (28 trang), tổng **51 trang, 158.144 ký tự**. Loại Key Terms, Summary, Review Questions, Critical Thinking và Personal Application. Không có trang bị loại do lỗi (`load_errors.json` rỗng).
- **Chuẩn hóa, lỗi và giới hạn:** Unicode NFC, bỏ nbsp và soft hyphen, mỗi block văn bản của PyMuPDF là một đoạn. Chân trang ("Access for free at openstax.org", số trang in) và chú thích hình vẫn nằm lẫn trong text. Bảng không được xử lý riêng (ví dụ Table 1.1). Chunk được cắt theo từng trang nên câu vắt qua hai trang bị tách.
- **Embedding model/provider/version/số chiều, vector store/version, metric, lệnh chạy và chi phí:** Sentence Transformers `intfloat/multilingual-e5-base` chạy local, 768 chiều, prefix `query:`/`passage:`, vector được normalize. PostgreSQL 16.16 + pgvector 0.8.7 (image `pgvector/pgvector:0.8.7-pg16`), metric cosine, tìm kiếm exact (không tạo index vector). Chi phí 0..
  Lệnh chạy:
  ```cmd
  docker compose up -d
  python -m src.load
  python -m src.run ingest
  python -m src.run eval --split dev
  python -m src.run eval --split test
  ```
- **Metadata bắt buộc, trường lọc bổ sung, nguồn giá trị và lý do chọn:** Bắt buộc có `document_id`, `source`, `page` (số trang PDF). Trường lọc thêm là `section` ("Chapter 1" hoặc "Chapter 2"), kiểu chuỗi, lấy từ phạm vi chương trong `configs/corpus.yaml`, không tự suy diễn. Lý do chọn: hai chương có nhiều chủ đề trùng nhau (APA, Brown v. Board, Freud) nên filter thực sự có tác dụng.

## Cấu hình và benchmark
- **A / B / C (tham số cụ thể, khác biệt duy nhất B–C):**
  - A: cửa sổ cố định 500 ký tự, overlap 50, không lọc.
  - B: gộp theo đoạn, tối đa 800 ký tự, đoạn dài tách theo câu, không lọc.
  - C: chunk giống hệt B, dùng chung bảng `chunks_b`. Khác biệt duy nhất B–C là điều kiện `WHERE section = ...`, chỉ áp dụng cho câu có filter.
- **≥20 câu: phân chia, câu metadata filter, cách kiểm chứng evidence:** 20 câu, 15 dev / 5 test. Test dùng các trang 29, 36, 68, 72, 74, không trùng trang với câu dev. Có 5 câu filter (q05, q06, q07 ở dev; q16, q17 ở test). Giá trị filter lấy từ câu hỏi ("In the introductory chapter…"), không lấy từ gold. Mỗi `evidence_quote` được `validate_bench.py` kiểm tra nằm trong trang gold sau chuẩn hóa (kết quả: tất cả OK).
- **Tiêu chí chọn chiến lược đã chốt trước khi xem test:** Ưu tiên Evidence Hit@3 trên dev; nếu hòa thì xét Hit@1; nếu vẫn hòa thì xét grounding thủ công, rồi tài nguyên (số chunk, thời gian ingest). Tiêu chí này được đề xuất sau khi có kết quả dev và trước khi chạy test (`eval --split test` chạy đúng một lần, không chỉnh cấu hình sau đó). **Không có mốc giờ ghi nhận** cho thời điểm chốt tiêu chí. Hạn chế: vì đã thấy kết quả dev khi chốt, tiêu chí có thể thiên về chiến lược đang dẫn đầu (C); test chưa bị dùng để điều chỉnh bất cứ gì.

## Kết quả

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian | Chi phí |
|---|---|---|---|---|---|---|
| A | dev | 6/15 | 12/15 | 374 | 26,77 s (lần 2: 26,56 s) | 0 |
| B | dev | 10/15 | 12/15 | 279 | 23,39 s (lần 2: 23,33 s) | 0 |
| C | dev | 11/15 | 13/15 | 279 (dùng bảng B) | không ingest riêng | 0 |
| A | test | 4/5 | 5/5 | 374 | như trên | 0 |
| B | test | 5/5 | 5/5 | 279 | như trên | 0 |
| C | test | 5/5 | 5/5 | 279 | như trên | 0 |

Thời gian gồm chunk, embed trên CPU và ghi DB. Nạp lần hai cho `rows_in_db` không đổi (374 và 279), nên upsert idempotent.

| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N hoặc N/A) | Grounding 0/1/2 (số câu) và trung bình /2 |
|---|---|---|---|---|
| A | 1,0 (10) | 15/15 | N/A | 0/1/4, TB 1,8 |
| B | 1,6 (10) | 15/15 | N/A | 0/0/5, TB 2,0 |
| C | 1,6 (chunk giống B) | 15/15 | 2/2 | 0/0/5, TB 2,0 |

**Ánh xạ mã ẩn (từ `label_key_DO_NOT_OPEN.csv`, mở sau khi chấm xong):** coherence X = B, Y = A; metadata và grounding S1 = B, S2 = A, S3 = C.

**Phương pháp chấm:** Nhãn do tác giả chấm thủ công, có Claude soạn nháp; tác giả đã rà soát và chỉnh sửa **[ĐIỀN: X]**/80 dòng (20 coherence + 15 grounding + 45 metadata). Tên cấu hình được che bằng mã khi chấm. Nguy cơ thiên lệch: một người chấm, đã biết trước giả thuyết A kém B.

**Chú thích:**
- Coherence: 10 vị trí cố định (đoạn giữa của PDF 19–28), cùng vị trí cho A và B; C dùng chunk của B nên điểm bằng B.
- Grounding: 5 câu test × top-3, thang 0/1/2, chỉ đánh giá bằng chứng truy xuất, không phải độ chính xác câu trả lời LLM. Quy tắc: điểm 2 nếu top-3 có chunk chứa trọn evidence và đúng nguồn; q16 ở A bị hạ xuống 1 vì hạng 1 sai trang/chương.
- Metadata: kiểm tra `source`, `page`, `section` của 15 bản ghi mỗi cấu hình so với `pages.jsonl`, chưa so với PDF gốc, nên phép kiểm này yếu.
- Filter: A và B không lọc nên N/A; C có 2 câu filter (q16, q17), cả hai top-3 đều đúng chương.
- Trường hữu ích: `page` giúp truy vết nguồn, `section` giúp lọc phạm vi. Hạn chế: `section` chỉ có hai giá trị nên lọc thô và không cứu được nhiễu cùng chương (q11, q14 ở dev).


## Phân tích và kết luận
- **So sánh A–B và B–C; 2 ví dụ sai:**
  - A→B: Hit@1 dev tăng từ 6/15 lên 10/15, Hit@3 giữ 12/15 nhưng câu sai khác nhau (A sai q04, q10, q11; B sai q06, q11, q14). Test cùng chiều (4/5 lên 5/5). B có ít chunk hơn (279 so với 374) vì không có overlap.
  - B→C: C hơn B 1 câu ở Hit@1 và Hit@3 trên dev (q06 được sửa nhờ filter loại trang 29 của Chương 1). Trên test B và C bằng nhau.
  - Ví dụ sai 1: **q10 (A, dev, nguồn trang 40).** Top-3 đều đúng trang nhưng không chunk nào chứa trọn câu "licensed clinical psychologists can administer… psychiatrists can prescribe medications". Chunk hạng 1 kết thúc ở "licensed clinical psych" do cửa sổ cố định cắt giữa từ.
  - Ví dụ sai 2: **q14 (B và C, dev, gold trang 59).** Top-3 là trang 54 và 58 (hạn chế của các phương pháp khác). Filter `Chapter 2` không giúp vì nhiễu nằm cùng chương.
- **Chiến lược chọn, đánh đổi, điều kiện áp dụng:** Chọn C theo tiêu chí đã nêu, với điều kiện filter chỉ có lợi khi người dùng cung cấp chương trước truy xuất. Với câu không có filter, C chạy giống B. Đánh đổi: C cần metadata đáng tin và ngữ cảnh người dùng; nếu không có filter thì B là lựa chọn an toàn.
- **Hạn chế:** Test chỉ 5 câu, 1 câu bằng 20 điểm phần trăm, nên không kết luận chắc chắn B hay C tốt hơn; test cũng dễ vì chủ đề tương đối riêng biệt. Nhãn thủ công do một người chấm, có Claude soạn nháp, nên có nguy cơ thiên lệch và điểm coherence phụ thuộc cách đọc thang. Metadata 15/15 yếu vì đối chiếu với `pages.jsonl` do chính pipeline tạo, chưa phải PDF gốc. Thời gian đo trên một máy và gồm embed trên CPU. Mọi kết luận chỉ trong phạm vi corpus này.
- **Nếu làm lại hoặc mở rộng:** chunk theo heading và cho phép vắt qua trang, thêm trường lọc mịn hơn (mục x.y), mở rộng benchmark vượt 20 câu, thử hybrid BM25 + dense, và có người thứ hai chấm nhãn.
