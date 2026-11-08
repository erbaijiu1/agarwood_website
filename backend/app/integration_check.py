"""Run the V1 API smoke flow against a running local backend container."""

import io
import json
import os
import time
import urllib.error
import urllib.request

from PIL import Image


BASE_URL = os.getenv("TEST_BASE_URL", "http://127.0.0.1:8000/api")
USERNAME = os.getenv("ADMIN_USERNAME", "admin")
PASSWORD = os.environ["ADMIN_PASSWORD"]


def request(path, method="GET", data=None, token=None, content_type="application/json"):
    body = None
    if data is not None:
        body = data if isinstance(data, bytes) else json.dumps(data).encode()
    headers = {"Content-Type": content_type}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE_URL + path, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return exc.code, json.loads(raw) if raw else None


def expect(status, expected, label):
    if status != expected:
        raise AssertionError(f"{label}: expected HTTP {expected}, got {status}")


def upload(token, image_format):
    image = Image.new("RGB", (12, 12), (88, 62, 36))
    image_data = io.BytesIO()
    image.save(image_data, format=image_format)
    extension = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}[image_format]
    boundary = f"agarwood-{time.time_ns()}"
    payload = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="test.{extension}"\r\n'
        f"Content-Type: image/{extension}\r\n\r\n"
    ).encode() + image_data.getvalue() + f"\r\n--{boundary}--\r\n".encode()
    return request(
        "/v1/admin/upload",
        "POST",
        payload,
        token,
        f"multipart/form-data; boundary={boundary}",
    )


def main():
    results = {}
    status, _ = request("/health")
    expect(status, 200, "health")

    status, _ = request("/v1/admin/products")
    expect(status, 401, "admin auth guard")
    status, _ = request(
        "/v1/admin/login", "POST", {"username": USERNAME, "password": "definitely-wrong"}
    )
    expect(status, 401, "wrong login")
    status, login = request(
        "/v1/admin/login", "POST", {"username": USERNAME, "password": PASSWORD}
    )
    expect(status, 200, "admin login")
    token = login["access_token"]

    status, categories = request("/v1/admin/categories", token=token)
    expect(status, 200, "categories")
    suffix = str(time.time_ns())
    product = {
        "name": "集成测试沉香",
        "slug": f"integration-agarwood-{suffix}",
        "sku": f"IT-{suffix}",
        "category_id": categories[0]["id"],
        "summary": "新增流程测试",
        "description": "用于 V1.0 自动化回归。",
        "image": "/agarwood/assets/product-chips.webp",
        "images": ["/agarwood/assets/product-chips.webp"],
        "origin": "测试产地说明",
        "scent": "测试木香",
        "usage": "集成测试",
        "price_mode": "inquiry",
        "price": None,
        "unit": "件",
        "stock_status": "available",
        "status": "published",
        "featured": False,
        "sort_order": 999,
    }
    status, created = request("/v1/admin/products", "POST", product, token)
    expect(status, 200, "create product")
    product_id = created["id"]
    status, public_product = request(f"/v1/products/{product['slug']}")
    expect(status, 200, "published product visible")

    product.update(
        summary="修改流程测试",
        price_mode="fixed",
        price=299.0,
        status="hidden",
    )
    status, _ = request(f"/v1/admin/products/{product_id}", "PUT", product, token)
    expect(status, 200, "modify and hide product")
    status, _ = request(f"/v1/products/{product['slug']}")
    expect(status, 404, "hidden product unavailable")
    product["status"] = "published"
    status, _ = request(f"/v1/admin/products/{product_id}", "PUT", product, token)
    expect(status, 200, "republish product")
    status, public_product = request(f"/v1/products/{product['slug']}")
    expect(status, 200, "republished product visible")
    if public_product["summary"] != "修改流程测试" or public_product["price"] != 299.0:
        raise AssertionError("modified product fields were not persisted")

    upload_urls = {}
    for image_format in ("JPEG", "PNG", "WEBP"):
        status, uploaded = upload(token, image_format)
        expect(status, 200, f"upload {image_format}")
        upload_urls[image_format] = uploaded["url"]
    boundary = "agarwood-invalid"
    invalid = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="invalid.svg"\r\n'
        "Content-Type: image/svg+xml\r\n\r\n"
        "<svg></svg>\r\n"
        f"--{boundary}--\r\n"
    ).encode()
    status, _ = request(
        "/v1/admin/upload",
        "POST",
        invalid,
        token,
        f"multipart/form-data; boundary={boundary}",
    )
    expect(status, 400, "reject invalid image")

    status, inquiry = request(
        "/v1/inquiries",
        "POST",
        {
            "name": "集成测试客户",
            "contact": "integration@example.com",
            "channel": "email",
            "message": "请提供测试商品详情",
            "product_id": product_id,
        },
    )
    expect(status, 201, "create inquiry")
    status, inquiries = request("/v1/admin/inquiries", token=token)
    expect(status, 200, "list inquiries")
    inquiry_row = next(row for row in inquiries if row["product_id"] == product_id)
    status, updated_inquiry = request(
        f"/v1/admin/inquiries/{inquiry_row['id']}", "PUT", {"status": "contacted"}, token
    )
    expect(status, 200, "update inquiry")
    if updated_inquiry["status"] != "contacted":
        raise AssertionError("inquiry status was not persisted")
    status, _ = request(f"/v1/admin/products/{product_id}", "DELETE", token=token)
    expect(status, 400, "protect product with inquiry")

    results.update(
        ok=True,
        product_id=product_id,
        product_slug=product["slug"],
        inquiry_id=inquiry_row["id"],
        upload_urls=upload_urls,
    )
    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
