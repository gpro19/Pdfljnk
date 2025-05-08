import os
import secrets
from datetime import datetime, timedelta
from flask import Flask, send_from_directory
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
import threading

# Config
UPLOAD_FOLDER = '/app/uploads'
EXPIRY_MINUTES = 10
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Database sederhana
file_db = {}

# Flask App (untuk download)
flask_app = Flask(__name__)
flask_app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Telegram Bot
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')

def generate_token():
    return secrets.token_urlsafe(12)

async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "📎 Kirim file PDF untuk mendapatkan link download Koyeb\n"
        "🔗 Link aktif 10 menit"
    )

async def handle_pdf(update: Update, context: CallbackContext):
    if not update.message.document:
        return

    file = await update.message.document.get_file()
    filename = update.message.document.file_name
    
    if not filename.lower().endswith('.pdf'):
        await update.message.reply_text("❌ Hanya file PDF yang diterima")
        return

    # Download file
    token = generate_token()
    save_path = os.path.join(UPLOAD_FOLDER, f"{token}.pdf")
    await file.download_to_drive(save_path)

    # Simpan info file
    file_db[token] = {
        'filename': f"{token}.pdf",
        'expiry': datetime.now() + timedelta(minutes=EXPIRY_MINUTES)
    }

    # Generate Koyeb link
    koyeb_url = f"https://{os.getenv('KOYEB_APP_NAME')}.koyeb.app/download/{token}"
    
    await update.message.reply_text(
        f"✅ File berhasil diupload!\n"
        f"🔗 Link download (10 menit):\n{koyeb_url}\n\n"
        f"📌 Klik link di atas untuk download"
    )

@flask_app.route('/download/<token>')
def download_file(token):
    if token not in file_db:
        return "Link tidak valid", 404

    file_info = file_db[token]
    
    if datetime.now() > file_info['expiry']:
        # Hapus file expired
        os.remove(os.path.join(flask_app.config['UPLOAD_FOLDER'], file_info['filename']))
        del file_db[token]
        return "Link sudah kadaluwarsa", 410
    
    return send_from_directory(
        flask_app.config['UPLOAD_FOLDER'],
        file_info['filename'],
        as_attachment=True
    )

def cleanup():
    now = datetime.now()
    expired = [token for token, data in file_db.items() if now > data['expiry']]
    
    for token in expired:
        file_path = os.path.join(UPLOAD_FOLDER, file_db[token]['filename'])
        if os.path.exists(file_path):
            os.remove(file_path)
        del file_db[token]
    
    threading.Timer(300, cleanup).start()  # Run every 5 minutes

def run_flask():
    flask_app.run(host='0.0.0.0', port=8000)

if __name__ == '__main__':
    # Mulai Flask di thread terpisah
    threading.Thread(target=run_flask, daemon=True).start()
    
    # Mulai pembersihan file
    cleanup()
    
    # Jalankan bot Telegram
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_pdf))
    app.run_polling()
