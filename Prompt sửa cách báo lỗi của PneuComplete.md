Hãy sửa toàn bộ Rule Engine của PneuComplete theo nguyên tắc sau:

Khi engine gặp bất kỳ vấn đ�? nào, **không giải thích dài dòng**.

Chỉ cần trả v�?:

**1. Sai ở đâu**  
→ Component / dữ liệu / field nào đang thiếu hoặc sai.

**2. Cần sửa gì**  
→ Chỉ rõ field ngư�?i dùng cần sửa.

**3. Sửa như thế nào**  
→ Giá trị hoặc lựa ch�?n cần nhập/ch�?n.

Ví dụ:

```text
R-VLV-01
�?� Chưa xác định được van cho Cylinder C01

Sai ở:
→ valve_function

Cần sửa:
→ Ch�?n valve_function cho C01
```

Nếu có nhi�?u lựa ch�?n thì đưa các lựa ch�?n để ngư�?i dùng ch�?n.

Nếu engine đã đủ dữ liệu và tự quyết định được thì **không h�?i ngư�?i dùng**.

Nếu có nhi�?u vấn đ�? thì tách từng Rule riêng.

**�?p dụng nguyên tắc này cho tất cả Rule trong phần m�?m**, không chỉ R-VLV-01 và R-FRL-01.

Các thông tin như catalog, model bị loại, Cv, AFM, trang tài liệu, logic phân tích... chỉ đưa vào **Chi tiết/Debug**, không đưa vào thông báo chính.