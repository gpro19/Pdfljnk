import os
import secrets
from datetime import datetime, timedelta
from flask import Flask, send_from_directory
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
import threading
from werkzeug.utils import secure_filename

# Konfigurasi
UPLOAD_FOLDER = '/app/uploads'
EXPIRY_MINUTES = 10
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Database sederhana
file_db = {}

# Flask App
flask_app = Flask(__name__)
flask_app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Telegram Bot
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')

def generate_token():
    return secrets.token_urlsafe(12)

async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "📎 Kirim file PDF untuk mendapatkan link download\n"
        "🔗 Link aktif 10 menit\n"
        "📝 File akan保持原始文件名 ketika diunduh"
    )

async def handle_pdf(update: Update, context: CallbackContext):
    if not update.message.document:
        return

    file = await update.message.document.get_file()
    original_name = secure_filename(update.message.document.file_name)
    
    if not original_name.lower().endswith('.pdf'):
        await update.message.reply_text("❌ Hanya file PDF yang diterima")
        return

    # Generate token unik
    token = generate_token()
    saved_name = f"{token}.pdf"
    save_path = os.path.join(flask_app.config['UPLOAD_FOLDER'], saved_name)
    
    # Download file
    await file.download_to_drive(save_path)

    # Simpan metadata
    file_db[token] = {
        'saved_name': saved_name,
        'original_name': original_name,
        'expiry': datetime.now() + timedelta(minutes=EXPIRY_MINUTES)
    }

    # Generate download link
    koyeb_url = f"https://anonymous-mommy-usgerbt-b8956f99.koyeb.app/download/{token}"
    
    await update.message.reply_text(
        f"✅ **{original_name}** berhasil diupload!\n"
        f"🔗 Download link (10 menit):\n{koyeb_url}\n\n"
        f"🔼 File akan diunduh sebagai: `{original_name}`",
        parse_mode='Markdown'
    )

@flask_app.route('/download/<token>')
def download_file(token):
    if token not in file_db:
        return "Link tidak valid atau sudah kadaluwarsa", 404
    
    file_info = file_db[token]
    
    # Cek expiry
    if datetime.now() > file_info['expiry']:
        # Hapus file
        file_path = os.path.join(flask_app.config['UPLOAD_FOLDER'], file_info['saved_name'])
        if os.path.exists(file_path):
            os.remove(file_path)
        del file_db[token]
        return "Link sudah kadaluwarsa", 410
    
    return send_from_directory(
        directory=flask_app.config['UPLOAD_FOLDER'],
        path=file_info['saved_name'],
        as_attachment=True,
        download_name=file_info['original_name']  # Nama file asli saat download
    )

def cleanup():
    now = datetime.now()
    expired = [token for token, data in file_db.items() if now > data['expiry']]
    
    for token in expired:
        file_path = os.path.join(UPLOAD_FOLDER, file_db[token]['saved_name'])
        if os.path.exists(file_path):
            os.remove(file_path)
        del file_db[token]
    
    threading.Timer(300, cleanup).start()  # Run every 5 minutes

def run_flask():
    flask_app.run(host='0.0.0.0', port=8000)

if __name__ == '__main__':
    # Jalankan Flask di thread terpisah
    threading.Thread(target=run_flask, daemon=True).start()
    
    # Mulai cleanup job
    cleanup()
    
    # Jalankan bot Telegram
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.PDF & ~filters.COMMAND, handle_pdf))
    app.run_polling()
