import os
import secrets
from datetime import datetime, timedelta
from flask import Flask, send_from_directory, abort
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
import threading
from werkzeug.utils import secure_filename
from urllib.parse import quote

# Configuration
UPLOAD_FOLDER = '/app/uploads'
EXPIRY_MINUTES = 10
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

file_db = {}
flask_app = Flask(__name__)
flask_app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')

def generate_token():
    return secrets.token_urlsafe(12) + '.pdf'  # Langsung tambahkan .pdf di token

async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "PDF Download Bot\n\n"
        "Send a PDF file for download link\n"
        "Link expires in 10 minutes\n\n"
        "Just attach your PDF file"
    )

async def handle_pdf(update: Update, context: CallbackContext):
    if not update.message.document:
        return

    file = await update.message.document.get_file()
    original_name = secure_filename(update.message.document.file_name)
    
    if not original_name.lower().endswith('.pdf'):
        await update.message.reply_text("Error: Only PDF files accepted")
        return

    token = generate_token()
    save_path = os.path.join(flask_app.config['UPLOAD_FOLDER'], token)
    
    await file.download_to_drive(save_path)

    file_db[token] = {
        'filename': token,
        'original_name': original_name,
        'expiry': datetime.now() + timedelta(minutes=EXPIRY_MINUTES)
    }

    safe_name = quote(original_name)
    download_url = f"https://anonymous-mommy-usgerbt-b8956f99.koyeb.app/download/{safe_name}.pdf"
    
    message = (
        f"File processed: {original_name}\n\n"
        f"Download link (expires in {EXPIRY_MINUTES} minutes):\n"
        f"{download_url}\n\n"
        f"Will download as: {original_name}"
    )
    
    await update.message.reply_text(message)

@flask_app.route('/download/<path:filename>.pdf')
def download_file(filename):
    # Decode URL-encoded filename
    original_name = filename + '.pdf'
    
    # Find matching file (compare decoded names)
    for token, data in file_db.items():
        if quote(data['original_name']) == filename:
            if datetime.now() > data['expiry']:
                os.remove(os.path.join(flask_app.config['UPLOAD_FOLDER'], token))
                del file_db[token]
                abort(410)
            
            return send_from_directory(
                flask_app.config['UPLOAD_FOLDER'],
                token,
                as_attachment=True,
                download_name=data['original_name']
            )
    
    abort(404)

def cleanup():
    now = datetime.now()
    for token in [t for t, data in file_db.items() if now > data['expiry']]:
        os.remove(os.path.join(UPLOAD_FOLDER, token))
        del file_db[token]
    
    threading.Timer(300, cleanup).start()

def run_flask():
    flask_app.run(host='0.0.0.0', port=8000)

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    cleanup()
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.PDF & ~filters.COMMAND, handle_pdf))
    app.run_polling()
