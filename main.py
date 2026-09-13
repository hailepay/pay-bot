 import os
import re
import io
import sqlite3
import threading
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
import pytesseract
from PIL import Image

conn = sqlite3.connect('payments.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS txns (
        txn_id TEXT PRIMARY KEY,
        amount TEXT,
        raw TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
''')
conn.commit()

app = Flask(__name__)

@app.route('/sms', methods=['POST'])
def receive_sms():
    data = request.json or request.form
    text = data.get('content', '') or data.get('message', '') or ''
    match = re.search(r'([A-Z0-9]{8,12})', text)
    if match:
        txn_id = match.group(1)
        cursor.execute('INSERT OR IGNORE INTO txns (txn_id, raw) VALUES (?, ?)', (txn_id, text))
        conn.commit()
        return jsonify({"status": "saved", "txn_id": txn_id}), 200
    return jsonify({"status": "ignored"}), 200

async def verify_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("🔍 ደረሰኙን በመመርመር ላይ...")
    try:
        photo_file = await update.message.photo[-1].get_file()
        img_bytes = await photo_file.download_as_bytearray()
        extracted_text = pytesseract.image_to_string(Image.open(io.BytesIO(img_bytes)))
        cursor.execute('SELECT txn_id, created_at FROM txns')
        records = cursor.fetchall()
        found = False
        matched_id = ""
        for rec in records:
            if rec[0] in extracted_text and len(rec[0]) >= 8:
                found = True
                matched_id = rec[0]
                break
        if found:
            msg = f"✅ **ክፍያው በትክክል ተረጋግጧል!**\n\n💳 **Txn ID:** `{matched_id}`\nይህ ትክክለኛ የባንክ ክፍያ ነው። እቃውን መስጠት ይቻላል።"
        else:
            msg = "❌ **የተላከው ደረሰኝ በሲስተሙ አልተገኘም!**\n\nይህ ደረሰኝ በባንክ SMS አልደረሰንም ወይም ሐሰተኛ ሊሆን ይችላል። እባክዎትን በጥንቃቄ ያረጋግጡ።"
        await status_msg.edit_text(msg, parse_mode='Markdown')
    except Exception as e:
        await status_msg.edit_text(f"⚠️ ስህተት ተፈጥሯል: {str(e)}")

def run_flask():
    app.run(host='0.0.0.0', port=5000)

t = threading.Thread(target=run_flask)
t.daemon = True
t.start()

bot_token = "8564504241:AAE09419EqW_vD09xdXW7C1s2aDuT7eZknk"
application = ApplicationBuilder().token(bot_token).build()
application.add_handler(MessageHandler(filters.PHOTO, verify_photo))
application.run_polling()
