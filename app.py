import os
import secrets
import re
from datetime import datetime, timedelta
from flask import Flask, send_from_directory, abort
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
import threading
from werkzeug.utils import secure_filename

# Configuration
UPLOAD_FOLDER = '/app/uploads'
EXPIRY_MINUTES = 10
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Simple database
file_db = {}

# Flask App
flask_app = Flask(__name__)
flask_app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Telegram Bot
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')

def generate_token():
    return secrets.token_urlsafe(12)

def escape_markdown(text):
    """Escape special Markdown characters"""
    escape_chars = r'\_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(
        escape_markdown(
            "PDF Download Bot\n\n"
            "Send me a PDF file to get a secure download link.\n"
            "Links expire after 10 minutes.\n\n"
            "Just attach a PDF file to begin."
        ),
        parse_mode='MarkdownV2'
    )

async def handle_pdf(update: Update, context: CallbackContext):
    if not update.message.document:
        return

    file = await update.message.document.get_file()
    original_name = secure_filename(update.message.document.file_name)
    
    if not original_name.lower().endswith('.pdf'):
        await update.message.reply_text("Error: Only PDF files are accepted")
        return

    token = generate_token()
    saved_name = f"{token}.pdf"
    save_path = os.path.join(flask_app.config['UPLOAD_FOLDER'], saved_name)
    await file.download_to_drive(save_path)

    file_db[token] = {
        'saved_name': saved_name,
        'original_name': original_name,
        'expiry': datetime.now() + timedelta(minutes=EXPIRY_MINUTES)
    }

    download_url = f"https://{os.getenv('KOYEB_APP_NAME')}.koyeb.app/download/{token}.pdf"
    
    message_text = escape_markdown(
        f"PDF successfully processed: {original_name}\n\n"
        f"Download link (expires in {EXPIRY_MINUTES} minutes):\n"
        f"{download_url}\n\n"
        f"File will download as: {original_name}"
    )
    
    await update.message.reply_text(
        message_text,
        parse_mode='MarkdownV2',
        disable_web_page_preview=True
    )

@flask_app.route('/download/<token>.pdf')
def download_file(token):
    if token not in file_db:
        abort(404)
    
    file_info = file_db[token]
    
    if datetime.now() > file_info['expiry']:
        file_path = os.path.join(flask_app.config['UPLOAD_FOLDER'], file_info['saved_name'])
        if os.path.exists(file_path):
            os.remove(file_path)
        del file_db[token]
        abort(410)
    
    return send_from_directory(
        flask_app.config['UPLOAD_FOLDER'],
        file_info['saved_name'],
        as_attachment=True,
        download_name=file_info['original_name']
    )

def cleanup():
    now = datetime.now()
    expired = [token for token, data in file_db.items() if now > data['expiry']]
    
    for token in expired:
        file_path = os.path.join(UPLOAD_FOLDER, file_db[token]['saved_name'])
        if os.path.exists(file_path):
            os.remove(file_path)
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
