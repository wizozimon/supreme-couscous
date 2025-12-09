import os
import uuid
from urllib.parse import quote
import socket

import boto3
from flask import Flask, request, redirect, url_for, send_from_directory, render_template_string, abort
from werkzeug.utils import secure_filename
from pathlib import Path

app = Flask(__name__)

PORT = int(os.getenv("PORT", "5001"))


def get_local_ip() -> str:
    """Вернуть локальный IP, по которому тебя видят другие устройства в сети."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Не делаем реальное подключение, просто используем маршрут до внешнего адреса,
        # чтобы узнать, какой IP используется в этой сети.
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()

# Локальная папка для хранения файлов (на этом ноуте/ПК)
STORAGE_DIR = Path.home() / "file_storage_site"
STORAGE_DIR.mkdir(exist_ok=True)

# Настройки (опциональные) для Yandex Object Storage или другого S3-совместимого хранилища
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "https://storage.yandexcloud.net")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY")
S3_BUCKET = os.getenv("S3_BUCKET")

USE_S3 = bool(S3_ACCESS_KEY and S3_SECRET_KEY and S3_BUCKET)

if USE_S3:
    s3_client = boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
    )
else:
    s3_client = None

# Максимальный размер файла (например, 100 МБ)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024


HTML_FORM = """
<!doctype html>
<html lang=\"ru\">
<head>
  <meta charset=\"utf-8\">
  <title>Файловое хранилище</title>
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif;
      background: radial-gradient(circle at top left, #4f46e5, #111827);
      color: #e5e7eb;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .container {
      background: rgba(17,24,39,0.92);
      border-radius: 24px;
      padding: 32px 32px 28px;
      width: 100%;
      max-width: 520px;
      box-shadow:
        0 20px 40px rgba(0,0,0,0.6),
        0 0 0 1px rgba(156,163,175,0.18);
      border: 1px solid rgba(129,140,248,0.5);
      backdrop-filter: blur(18px);
    }
    h1 {
      margin: 0 0 6px;
      font-size: 26px;
      color: #f9fafb;
    }
    .subtitle {
      margin: 0 0 22px;
      font-size: 14px;
      color: #9ca3af;
    }
    form {
      display: flex;
      flex-direction: column;
      gap: 12px;
      margin-bottom: 18px;
    }
    .file-input-wrapper {
      position: relative;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .file-input-wrapper label {
      flex-shrink: 0;
      padding: 9px 14px;
      border-radius: 999px;
      border: 1px dashed rgba(129,140,248,0.7);
      color: #e5e7eb;
      font-size: 13px;
      cursor: pointer;
      background: rgba(55,65,81,0.7);
      transition: background 0.15s ease, border-color 0.15s ease, transform 0.05s ease;
    }
    .file-input-wrapper label:hover {
      background: rgba(129,140,248,0.25);
      border-color: #a5b4fc;
      transform: translateY(-1px);
    }
    .file-input-wrapper span {
      font-size: 13px;
      color: #9ca3af;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    input[type=file] {
      position: absolute;
      inset: 0;
      opacity: 0;
      cursor: pointer;
    }
    button[type=submit] {
      margin-top: 4px;
      border: none;
      border-radius: 999px;
      padding: 10px 18px;
      font-size: 14px;
      font-weight: 500;
      color: #f9fafb;
      background: linear-gradient(90deg, #6366f1, #8b5cf6);
      cursor: pointer;
      box-shadow: 0 10px 25px rgba(79,70,229,0.6);
      transition: transform 0.09s ease, box-shadow 0.09s ease, filter 0.1s ease;
      align-self: flex-start;
    }
    button[type=submit]:hover {
      filter: brightness(1.06);
      transform: translateY(-1px);
      box-shadow: 0 14px 30px rgba(79,70,229,0.75);
    }
    button[type=submit]:active {
      transform: translateY(0px) scale(0.99);
      box-shadow: 0 8px 18px rgba(79,70,229,0.5);
    }
    .result {
      margin-top: 10px;
      padding-top: 12px;
      border-top: 1px solid rgba(55,65,81,0.9);
    }
    .result-title {
      font-size: 15px;
      margin: 0 0 6px;
      color: #e5e7eb;
    }
    .result p {
      margin: 0;
      font-size: 13px;
      color: #9ca3af;
    }
    .link-box {
      margin-top: 8px;
      padding: 8px 10px;
      border-radius: 10px;
      background: rgba(31,41,55,0.9);
      border: 1px solid rgba(55,65,81,0.9);
      font-size: 13px;
      word-break: break-all;
    }
    .link-box a {
      color: #a5b4fc;
      text-decoration: none;
    }
    .link-box a:hover {
      text-decoration: underline;
    }
    .hint {
      margin-top: 8px;
      font-size: 11px;
      color: #6b7280;
    }
    @media (max-width: 600px) {
      .container {
        margin: 16px;
        padding: 22px 18px 18px;
      }
      h1 {
        font-size: 22px;
      }
    }
  </style>
</head>
<body>
  <div class=\"container\">
    <h1>Файловое хранилище</h1>
    <p class=\"subtitle\">Загрузи файл и получи быструю ссылку для скачивания прямо с этого компьютера.</p>

    <form method=\"post\" enctype=\"multipart/form-data\" action=\"{{ url_for('upload') }}\">
      <div class=\"file-input-wrapper\">
        <label>
          Выбрать файл
          <input type=\"file\" name=\"file\" onchange=\"document.getElementById('file-name').textContent = this.files[0] ? this.files[0].name : 'Файл не выбран';\">
        </label>
        <span id=\"file-name\">Файл не выбран</span>
      </div>
      <button type=\"submit\">Загрузить</button>
    </form>

    {% if link %}
    <div class=\"result\">
      <p class=\"result-title\">Файл загружен ✅</p>
      <p>Прямая ссылка для скачивания:</p>
      <div class=\"link-box\">
        <a href=\"{{ link }}\">{{ link }}</a>
      </div>
      <p class=\"hint\">Отправь эту ссылку тому, кому нужно скачать файл. Сайт должен быть запущен на этом компьютере.</p>
    </div>
    {% endif %}
  </div>
</body>
</html>
"""


@app.route("/", methods=["GET"])
def index():
    return render_template_string(HTML_FORM, link=None)


@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return "Нет файла в запросе", 400

    file = request.files["file"]
    if file.filename == "":
        return "Файл не выбран", 400

    filename = secure_filename(file.filename)
    if not filename:
        return "Недопустимое имя файла", 400

    # Если настроен S3 (например, Yandex Object Storage) — грузим туда
    if USE_S3 and s3_client is not None:
        object_key = f"uploads/{uuid.uuid4()}_{filename}"
        # file.stream — это файловый объект, который можно передать в upload_fileobj
        s3_client.upload_fileobj(file.stream, S3_BUCKET, object_key)

        # Публичная ссылка (при условии, что бакет/объекты доступны публично)
        s3_base_url = os.getenv("S3_PUBLIC_BASE_URL", f"https://storage.yandexcloud.net/{S3_BUCKET}")
        download_url = f"{s3_base_url}/{quote(object_key)}"
    else:
        # Локальное хранилище на этом ноуте / на сервере хостинга
        save_path = STORAGE_DIR / filename
        file.save(save_path)
        # Если задан PUBLIC_BASE_URL (например, домен/ngrok-адрес или кастомный домен) — используем его
        public_base = os.getenv("PUBLIC_BASE_URL")
        if public_base:
            public_base = public_base.rstrip("/")
            download_url = public_base + url_for("download_file", filename=filename)
        else:
            # Иначе строим абсолютный URL на основе домена, с которого пришёл запрос
            # Это корректно работает на хостингах (Render, Railway и т.п.)
            download_url = url_for("download_file", filename=filename, _external=True)

    return render_template_string(HTML_FORM, link=download_url)


@app.route("/f/<path:filename>", methods=["GET"])
def download_file(filename):
    safe_name = secure_filename(filename)
    if not safe_name:
        abort(404)

    file_path = STORAGE_DIR / safe_name
    if not file_path.is_file():
        abort(404)

    return send_from_directory(
        STORAGE_DIR,
        safe_name,
        as_attachment=True,
        download_name=safe_name,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=True)
