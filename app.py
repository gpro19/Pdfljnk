import os
import secrets
import re
from datetime import datetime, timedelta
from flask import Flask, send_from_directory, abort
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
import threading
from werkzeug.utils import secure_filename
from urllib.parse import quote, unquote

# ========== KONFIGURASI ==========
UPLOAD_FOLDER = '/app/uploads'
EXPIRY_MINUTES = 10
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

file_db = {}  # Database sederhana
flask_app = Flask(__name__)
flask_app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')

# ========== FUNGSI UTILITAS ==========
def generate_token():
    return secrets.token_urlsafe(12)

def make_url_friendly(filename):
    """
    Mengubah nama file menjadi format URL-friendly:
    1. Pertahankan alfabet, angka, strip, dan titik
    2. Ganti spasi dan karakter khusus dengan strip
    3. Konversi ke lowercase
    4. Pastikan ekstensi .pdf
    """
    # Pisahkan nama dan ekstensi
    base, ext = os.path.splitext(filename)
    
    # Bersihkan nama file
    clean = re.sub(r'[^\w\s-]', '', base).strip()
    clean = re.sub(r'[\s_-]+', '-', clean)
    
    # Gabungkan dengan ekstensi
    return f"{clean.lower()}.pdf"

# ========== HANDLER TELEGRAM ==========
async def start(update: Update, context: CallbackContext):
    welcome_msg = (
        "📚 *PDF Download Bot*\n\n"
        "Kirim file PDF untuk mendapatkan link download yang:\n"
        "- Berformat `NAMA_FILE.pdf`\n"
        "- Berlaku 10 menit\n"
        "- Download dengan nama asli\n\n"
        "Cukup lampirkan file PDF Anda"
    )
    await update.message.reply_text(welcome_msg, parse_mode='MarkdownV2')

async def handle_pdf(update: Update, context: CallbackContext):
    if not update.message.document:
        return

    file = await update.message.document.get_file()
    original_name = secure_filename(update.message.document.file_name)
    
    if not original_name.lower().endswith('.pdf'):
        await update.message.reply_text("❌ Hanya file PDF yang diterima")
        return

    token = f"{generate_token()}.pdf"  # Penyimpanan dengan ekstensi
    save_path = os.path.join(flask_app.config['UPLOAD_FOLDER'], token)
    
    await file.download_to_drive(save_path)

    file_db[token] = {
        'original_name': original_name,
        'expiry': datetime.now() + timedelta(minutes=EXPIRY_MINUTES)
    }

    url_name = make_url_friendly(original_name)
    download_url = f"https://anonymous-mommy-usgerbt-b8956f99.koyeb.app/download/{url_name}"
    
    await update.message.reply_text(
        f"✅ Berhasil mengunggah: `{original_name}`\n"
        f"🔗 [Download sekarang]({download_url}) (10 menit)\n"
        f"📝 Nama file akan dipertahankan",
        parse_mode='MarkdownV2',
        disable_web_page_preview=True
    )

# ========== ROUTE FLASK ==========
@flask_app.route('/download/<path:url_name>')
def download_file(url_name):
    # Normalisasi nama file dari URL
    if not url_name.lower().endswith('.pdf'):
        url_name += '.pdf'
    
    # Cari file yang cocok
    for token, data in file_db.items():
        if make_url_friendly(data['original_name']) == url_name.lower():
            if datetime.now() > data['expiry']:
                # Cleanup file expired
                file_path = os.path.join(flask_app.config['UPLOAD_FOLDER'], token)
                if os.path.exists(file_path):
                    os.remove(file_path)
                del file_db[token]
                abort(410, "Link sudah kadaluarsa")
            
            return send_from_directory(
                flask_app.config['UPLOAD_FOLDER'],
                token,
                as_attachment=True,
                download_name=data['original_name']
            )
    
    abort(404, "File tidak ditemukan")

# ========== MAINTENANCE ==========
def cleanup():
    now = datetime.now()
    expired = [t for t, data in file_db.items() if now > data['expiry']]
    
    for token in expired:
        try:
            os.remove(os.path.join(UPLOAD_FOLDER, token))
            del file_db[token]
        except:
            continue
    
    threading.Timer(300, cleanup).start()  # Jalankan setiap 5 menit

# ========== START APLIKASI ==========
def run_flask():
    flask_app.run(host='0.0.0.0', port=8000)

if __name__ == '__main__':
    # Jalankan Flask di thread terpisah
    threading.Thread(target=run_flask, daemon=True).start()
    
    # Mulai pembersihan
    cleanup()
    
    # Konfigurasi bot Telegram
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.PDF & ~filters.COMMAND, handle_pdf))
    
    print("Bot started...")
    app.run_polling()
